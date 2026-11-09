"""Credential loading, health probes and lightweight sync for iFinD / DataYes.

The platform's canonical lake is ``data/market.db`` (Tushare-based).  These
adapters let you *verify* and *pull* the sources you already subscribe to;
``sync`` is deliberately opt-in (``--write``) so a different vendor's data
cannot silently contaminate the research lake.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from alphaforge.utils import connect, dashed, transaction, upsert_frame

ROOT = Path(__file__).resolve().parents[3]
CRED_FILES = [
    ROOT / "config" / "credentials.json",
    Path.home() / "Quant" / "qQuant" / "quantlab" / "config" / "credentials.json",
]
ENV_KEYS = ["TUSHARE_TOKEN", "IFIND_REFRESH_TOKEN", "IFIND_ACCESS_TOKEN",
            "DATAYES_TOKEN", "DATAYES_BASE_URL"]

IFIND_BASE = "https://quantapi.51ifind.com/api/v1"
DATAYES_BASE = "https://gw.datayes.com"
DATAYES_DAILY = "/aladdin_proxy/data_api/api/market/getMktEqud.json"
DATAYES_CAL = "/aladdin_proxy/data_api/api/master/getTradeCal.json"


def credentials() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in CRED_FILES:
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                out.update({str(k): str(v) for k, v in doc.items() if v})
        except Exception:
            continue
    for key in ENV_KEYS:
        if os.environ.get(key):
            out[key] = os.environ[key]
    return out


def _mask(token: str) -> str:
    if not token:
        return ""
    return f"{token[:4]}…{token[-4:]}" if len(token) > 10 else "***"


def _get_json(url: str, headers: dict[str, str] | None = None,
              params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _post_json(url: str, payload: dict[str, Any],
               headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


# --------------------------------------------------------------------------
# status / probes
# --------------------------------------------------------------------------
_PROBE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PROBE_TTL = 120


def configured(source: str) -> bool:
    cred = credentials()
    if source == "tushare":
        return bool(cred.get("TUSHARE_TOKEN"))
    if source == "ifind":
        return bool(cred.get("IFIND_REFRESH_TOKEN") or cred.get("IFIND_ACCESS_TOKEN"))
    if source == "datayes":
        return bool(cred.get("DATAYES_TOKEN"))
    return False


def status(probe: bool = False) -> list[dict[str, Any]]:
    cred = credentials()
    rows = [
        {
            "id": "tushare", "name": "Tushare Pro", "role": "日线 / 复权 / 每日指标 / 财务 PIT / 涨跌停价",
            "configured": bool(cred.get("TUSHARE_TOKEN")),
            "token": _mask(cred.get("TUSHARE_TOKEN", "")),
            "capabilities": ["daily", "adj_factor", "daily_basic", "moneyflow", "stk_limit", "fina_pit"],
            "canonical": True,
        },
        {
            "id": "ifind", "name": "同花顺 iFinD", "role": "日线 / 实时快照 / 涨停池 / 一致预期",
            "configured": bool(cred.get("IFIND_REFRESH_TOKEN") or cred.get("IFIND_ACCESS_TOKEN")),
            "token": _mask(cred.get("IFIND_REFRESH_TOKEN") or cred.get("IFIND_ACCESS_TOKEN", "")),
            "capabilities": ["daily", "realtime", "limit_pool", "consensus"],
            "canonical": False,
        },
        {
            "id": "datayes", "name": "通联数据 DataYes", "role": "日线 / 累计复权因子 / 估值 / 指数 / 主题",
            "configured": bool(cred.get("DATAYES_TOKEN")),
            "token": _mask(cred.get("DATAYES_TOKEN", "")),
            "capabilities": ["daily", "accumAdjFactor", "valuation", "index", "concepts"],
            "canonical": False,
        },
    ]
    for row in rows:
        cached = _PROBE_CACHE.get(row["id"])
        if cached:
            row["probe"] = cached[1]
    if probe:
        for row in rows:
            if row["configured"]:
                try:
                    row["probe"] = probe_source(row["id"])
                except Exception as exc:
                    row["probe"] = {"ok": False, "message": str(exc)[:200]}
    return rows


def probe_source(source: str, use_cache: bool = True) -> dict[str, Any]:
    cached = _PROBE_CACHE.get(source)
    if use_cache and cached and time.time() - cached[0] < _PROBE_TTL:
        return cached[1]
    t0 = time.time()
    cred = credentials()
    try:
        if source == "tushare":
            doc = _post_json("https://api.tushare.pro", {
                "api_name": "trade_cal", "token": cred.get("TUSHARE_TOKEN", ""),
                "params": {"exchange": "SSE", "start_date": "20260101", "end_date": "20260110"},
                "fields": "cal_date,is_open"})
            ok = doc.get("code") == 0
            msg = "trade_cal ok" if ok else str(doc.get("msg"))[:120]
        elif source == "ifind":
            token = cred.get("IFIND_ACCESS_TOKEN", "")
            if not token:
                doc = _post_json(f"{IFIND_BASE}/get_access_token", {},
                                 {"refresh_token": cred.get("IFIND_REFRESH_TOKEN", "")})
                if doc.get("errorcode") not in (0, "0"):
                    ok, msg = False, str(doc.get("errmsg"))[:120]
                    raise RuntimeError(msg)
                token = (doc.get("data") or {}).get("access_token", "")
            doc = _post_json(f"{IFIND_BASE}/get_trade_dates", {
                "marketcode": "212001",
                "functionpara": {"mode": "1", "dateType": "0", "period": "D", "dateFormat": "0"},
                "startdate": "2026-01-01", "enddate": "2026-01-10",
            }, {"access_token": token})
            ok = doc.get("errorcode") in (0, "0")
            msg = "get_trade_dates ok" if ok else str(doc.get("errmsg"))[:120]
        elif source == "datayes":
            doc = _get_json(DATAYES_BASE + DATAYES_CAL, {
                "Authorization": "Bearer " + cred.get("DATAYES_TOKEN", "")}, {
                "exchangeCD": "XSHG", "beginDate": "20260101", "endDate": "20260110",
                "pagenum": 1, "pagesize": 5})
            rows = doc.get("data") if isinstance(doc, dict) else doc
            ok = isinstance(rows, list) and len(rows) > 0
            msg = f"getTradeCal ok ({len(rows)})" if ok else "empty response"
        else:
            ok, msg = False, "unknown source"
    except Exception as exc:
        ok, msg = False, str(exc)[:200]
    result = {"ok": bool(ok), "message": msg, "latency_ms": round((time.time() - t0) * 1000)}
    _PROBE_CACHE[source] = (time.time(), result)
    return result


# --------------------------------------------------------------------------
# DataYes daily bars
# --------------------------------------------------------------------------
def fetch_datayes_daily(codes: Iterable[str], start: str, end: str,
                        page_size: int = 5000) -> list[dict[str, Any]]:
    cred = credentials()
    token = cred.get("DATAYES_TOKEN", "")
    if not token:
        raise RuntimeError("未配置 DATAYES_TOKEN")
    out: list[dict[str, Any]] = []
    codes = [str(c).zfill(6) for c in codes]
    for i in range(0, len(codes), 40):
        chunk = codes[i:i + 40]
        page = 1
        while page <= 20:
            doc = _get_json(DATAYES_BASE + DATAYES_DAILY,
                            {"Authorization": "Bearer " + token},
                            {"ticker": ",".join(chunk), "beginDate": start.replace("-", ""),
                             "endDate": end.replace("-", ""), "pagenum": page,
                             "pagesize": page_size,
                             "field": "ticker,tradeDate,preClosePrice,openPrice,highestPrice,"
                                      "lowestPrice,closePrice,turnoverVol,turnoverValue,"
                                      "accumAdjFactor,turnoverRate,PE,PE1,PB,marketValue,"
                                      "negMarketValue,isOpen,vwap"})
            rows = doc.get("data") if isinstance(doc, dict) else doc
            if not rows:
                break
            out.extend(rows)
            if len(rows) < page_size:
                break
            page += 1
    return out


def sync_datayes(cfg, codes: Iterable[str], start: str, end: str,
                 write: bool = False) -> dict[str, Any]:
    rows = fetch_datayes_daily(codes, start, end)
    if not write:
        return {"source": "datayes", "fetched": len(rows), "written": 0,
                "sample": rows[:3]}
    conn = connect(cfg.paths.market_db)
    daily, adj, basic = [], [], []
    for r in rows:
        code = str(r.get("ticker") or "").zfill(6)
        d = dashed(str(r.get("tradeDate") or ""))
        if not code or not d:
            continue
        if not (r.get("closePrice") or 0) > 0:
            continue
        daily.append({
            "code": code, "date": d,
            "open": r.get("openPrice"), "high": r.get("highestPrice"),
            "low": r.get("lowestPrice"), "close": r.get("closePrice"),
            "pre_close": r.get("preClosePrice"),
            "volume": r.get("turnoverVol"), "amount": r.get("turnoverValue"),
        })
        adj.append({"code": code, "date": d,
                    "adj_factor": r.get("accumAdjFactor") or 1.0})
        basic.append({
            "code": code, "date": d,
            "turnover_f": r.get("turnoverRate"),
            "pe_ttm": r.get("PE1") or r.get("PE"),
            "pb": r.get("PB"),
            "total_mv": r.get("marketValue"),
            "circ_mv": r.get("negMarketValue"),
        })
    with transaction(conn):
        upsert_frame(conn, "daily", pd.DataFrame(daily), ["code", "date"])
        upsert_frame(conn, "adj_factor", pd.DataFrame(adj), ["code", "date"])
        upsert_frame(conn, "daily_basic", pd.DataFrame(basic), ["code", "date"])
    conn.close()
    return {"source": "datayes", "fetched": len(rows), "written": len(daily)}


# --------------------------------------------------------------------------
# iFinD daily bars
# --------------------------------------------------------------------------
def _ifind_token() -> str:
    cred = credentials()
    token = cred.get("IFIND_ACCESS_TOKEN", "")
    if token:
        return token
    doc = _post_json(f"{IFIND_BASE}/get_access_token", {},
                     {"refresh_token": cred.get("IFIND_REFRESH_TOKEN", "")})
    if doc.get("errorcode") not in (0, "0"):
        raise RuntimeError(f"iFinD token: {doc.get('errmsg')}")
    return (doc.get("data") or {}).get("access_token", "")


def fetch_ifind_daily(codes: Iterable[str], start: str, end: str,
                      adjust: str = "none") -> list[dict[str, Any]]:
    token = _ifind_token()
    cps = {"none": "1", "qfq": "2", "hfq": "3"}.get(adjust, "1")
    out = []
    for code in codes:
        code = str(code).zfill(6)
        suffix = ".SH" if code.startswith(("6", "9")) else ".SZ" if code.startswith(("0", "2", "3")) else ".BJ"
        doc = _post_json(f"{IFIND_BASE}/cmd_history_quotation", {
            "codes": code + suffix,
            "indicators": "open,high,low,close,preClose,volume,amount,changeRatio,turnoverRatio",
            "startdate": start, "enddate": end,
            "functionpara": {"Interval": "D", "CPS": cps, "Fill": "Previous"},
        }, {"access_token": token})
        if doc.get("errorcode") not in (0, "0"):
            continue
        for table in doc.get("tables") or []:
            times = table.get("time") or []
            cols = table.get("table") or {}
            for i, d in enumerate(times):
                def val(k):
                    arr = cols.get(k) or []
                    return arr[i] if i < len(arr) else None
                if val("close") in (None, 0):
                    continue
                out.append({
                    "code": code, "date": str(d),
                    "open": val("open"), "high": val("high"), "low": val("low"),
                    "close": val("close"), "pre_close": val("preClose"),
                    "volume": val("volume"), "amount": val("amount"),
                    "change_ratio": val("changeRatio"),
                    "turnover_f": (val("turnoverRatio") or 0) / 100.0 if val("turnoverRatio") is not None else None,
                    "adjust": adjust,
                })
    return out


def sync_ifind(cfg, codes: Iterable[str], start: str, end: str,
               adjust: str = "none", write: bool = False) -> dict[str, Any]:
    rows = fetch_ifind_daily(codes, start, end, adjust=adjust)
    if not write:
        return {"source": "ifind", "adjust": adjust, "fetched": len(rows), "written": 0,
                "sample": rows[:3]}
    conn = connect(cfg.paths.market_db)
    daily, adj, basic = [], [], []
    for r in rows:
        daily.append({k: r.get(k) for k in
                      ("code", "date", "open", "high", "low", "close", "pre_close", "volume", "amount")})
        adj.append({"code": r["code"], "date": r["date"],
                    "adj_factor": 1.0 if adjust != "none" else 1.0})
        basic.append({"code": r["code"], "date": r["date"],
                      "turnover_f": r.get("turnover_f")})
    with transaction(conn):
        upsert_frame(conn, "daily", pd.DataFrame(daily), ["code", "date"])
        upsert_frame(conn, "adj_factor", pd.DataFrame(adj), ["code", "date"])
        upsert_frame(conn, "daily_basic", pd.DataFrame(basic), ["code", "date"])
    conn.close()
    return {"source": "ifind", "adjust": adjust, "fetched": len(rows), "written": len(daily)}

