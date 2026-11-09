from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

from alphaforge.config import Config, load_config, resolve_token
from alphaforge.data import schema
from alphaforge.utils import (
    compact,
    connect,
    dashed,
    now_iso,
    shift_days,
    to_code,
    to_ts_code,
    upsert_frame,
    write_json,
)

API_URL = "http://api.tushare.pro"


class TushareError(RuntimeError):
    pass


class NoPermission(TushareError):
    pass


class RateLimiter:
    """Polite fixed-interval limiter with multiplicative penalty on throttling."""

    def __init__(self, interval: float = 0.13):
        self.base = interval
        self.interval = interval
        self.last = 0.0

    def wait(self) -> None:
        delta = time.monotonic() - self.last
        if delta < self.interval:
            time.sleep(self.interval - delta)
        self.last = time.monotonic()

    def penalize(self) -> None:
        self.interval = min(self.interval * 1.6, 3.0)

    def relax(self) -> None:
        self.interval = max(self.base, self.interval * 0.98)


@dataclass
class Stats:
    calls: int = 0
    rows: int = 0
    skipped: int = 0
    errors: int = 0
    started: float = field(default_factory=time.time)

    def eta(self, done: int, total: int) -> str:
        if done <= 0:
            return "-"
        rate = (time.time() - self.started) / done
        remain = max(total - done, 0) * rate
        return f"{remain / 60:.1f}min"


class TushareClient:
    def __init__(self, token: str, interval: float = 0.13, retries: int = 6):
        self.token = token
        self.session = requests.Session()
        self.limiter = RateLimiter(interval)
        self.retries = retries
        self.stats = Stats()

    def query(self, api_name: str, params: dict | None = None, fields: str = "") -> pd.DataFrame:
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": fields,
        }
        last_err: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait()
            try:
                resp = self.session.post(API_URL, json=payload, timeout=60)
                resp.raise_for_status()
                doc = resp.json()
            except Exception as exc:  # network hiccup
                last_err = exc
                time.sleep(min(2 ** attempt, 20))
                continue

            self.stats.calls += 1
            code = doc.get("code")
            if code == 0:
                data = doc.get("data") or {}
                cols = data.get("fields") or []
                items = data.get("items") or []
                self.stats.rows += len(items)
                self.limiter.relax()
                return pd.DataFrame(items, columns=cols) if items else pd.DataFrame(columns=cols)

            msg = str(doc.get("msg") or "")
            if code == 40203 or "权限" in msg or "积分" in msg:
                raise NoPermission(f"{api_name}: {msg}")
            if "每分钟" in msg or "频率" in msg or "超过" in msg or code in (-2001, 40204):
                self.limiter.penalize()
                time.sleep(min(5 * (attempt + 1), 30))
                last_err = TushareError(f"{api_name}: {msg}")
                continue
            raise TushareError(f"{api_name}: code={code} msg={msg}")
        raise TushareError(f"{api_name} 重试耗尽: {last_err}")


# --------------------------------------------------------------------------
# field conversions
# --------------------------------------------------------------------------
def _num(df: pd.DataFrame, col: str, scale: float = 1.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce") * scale


class Ingestor:
    DATASETS = ("daily", "adj_factor", "daily_basic", "moneyflow", "stk_limit", "fina")

    def __init__(self, cfg: Config, token: str | None = None, interval: float = 0.13):
        self.cfg = cfg
        self.token = token or resolve_token(cfg)
        self.client = TushareClient(self.token, interval=interval)
        self.conn = connect(cfg.paths.market_db)
        self.conn.executescript(schema.DDL)
        self.disabled: set[str] = set()
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", ("schema_version", "1")
        )
        self.conn.commit()

    # -- top level ---------------------------------------------------------
    def run(
        self,
        indices: list[str],
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
        codes: list[str] | None = None,
        skip: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        start = dashed(start or self.cfg.data_start)
        end = dashed(end or self.cfg.data_end)
        t0 = time.time()
        print(f"[ingest] 区间 {start} ~ {end}")

        self.sync_calendar(start, end)
        self.sync_securities()
        if codes:
            universe = [to_code(c) for c in codes]
        else:
            self.sync_index_members(indices, start, end)
            universe = self.build_universe(indices, start, end)
        if limit:
            universe = universe[:limit]
        print(f"[ingest] 股票池 {len(universe)} 只（指数 {indices}）")

        datasets = [d for d in self.DATASETS if d not in skip and d not in self.disabled]
        print(f"[ingest] 数据集 {datasets}")

        for i, code in enumerate(universe, 1):
            for ds in datasets:
                if ds in self.disabled:
                    continue
                try:
                    self.ingest_dataset(ds, code, start, end)
                except NoPermission as exc:
                    print(f"[warn] {ds} 无权限，已跳过: {exc}", file=sys.stderr)
                    self.disabled.add(ds)
                except Exception as exc:
                    self.client.stats.errors += 1
                    print(f"[error] {ds} {code}: {exc}", file=sys.stderr)
            if i % 25 == 0 or i == len(universe):
                st = self.client.stats
                print(
                    f"[ingest] {i}/{len(universe)} calls={st.calls} rows={st.rows} "
                    f"errors={st.errors} eta={st.eta(i, len(universe))}",
                    flush=True,
                )
            if i % 200 == 0:
                self.conn.commit()

        self.sync_index_daily(indices + [self.cfg.benchmark], start, end)
        self.finalize(indices, start, end)
        self.conn.commit()
        summary = {
            "start": start,
            "end": end,
            "universe": len(universe),
            "calls": self.client.stats.calls,
            "rows": self.client.stats.rows,
            "errors": self.client.stats.errors,
            "disabled": sorted(self.disabled),
            "elapsed_sec": round(time.time() - t0, 1),
        }
        write_json(self.cfg.paths.data / "ingest_summary.json", summary)
        print(f"[ingest] 完成 {json.dumps(summary, ensure_ascii=False)}")
        return summary

    # -- reference data ----------------------------------------------------
    def sync_calendar(self, start: str, end: str) -> None:
        df = self.client.query(
            "trade_cal",
            {"exchange": "SSE", "start_date": compact(shift_days(start, -400)),
             "end_date": compact(shift_days(end, 30))},
            "cal_date,is_open",
        )
        if df.empty:
            raise TushareError("trade_cal 返回为空")
        out = pd.DataFrame(
            {
                "date": df["cal_date"].map(dashed),
                "is_open": pd.to_numeric(df["is_open"], errors="coerce").fillna(1).astype(int),
            }
        ).drop_duplicates("date")
        upsert_frame(self.conn, "calendar", out, ["date"])
        self.conn.commit()
        # open dates must also include any date present in the daily table (defensive)
        print(f"[ingest] calendar {len(out)} rows")

    def sync_securities(self) -> None:
        frames = []
        status_map: dict[str, str] = {}
        for status in ("L", "D", "P"):
            try:
                df = self.client.query(
                    "stock_basic",
                    {"list_status": status},
                    "ts_code,symbol,name,industry,market,list_date,delist_date",
                )
            except NoPermission:
                continue
            if df.empty:
                continue
            frames.append(df)
            status_map.update({c: status for c in df["ts_code"]})
        if not frames:
            print("[warn] stock_basic 无数据")
            return
        raw = pd.concat(frames, ignore_index=True).drop_duplicates("ts_code")
        symbol = raw["symbol"].astype(str).str.zfill(6)
        out = pd.DataFrame(
            {
                "code": symbol,
                "ts_code": raw["ts_code"],
                "name": raw["name"],
                "industry": raw.get("industry", pd.Series(index=raw.index, dtype=object)),
                "market": raw.get("market"),
                "exchange": raw["ts_code"].str.split(".").str[-1],
                "board": symbol.map(
                    lambda c: "STAR" if c.startswith("688") else
                    "GEM" if c.startswith("30") else
                    "BSE" if c.startswith(("8", "4", "92")) else "MAIN"
                ),
                "list_date": raw["list_date"].map(lambda x: dashed(x) if x else None),
                "delist_date": raw["delist_date"].map(lambda x: dashed(x) if x else None),
                "is_st": raw["name"].astype(str).str.contains("ST", na=False).astype(int),
                "list_status": raw["ts_code"].map(status_map),
                "updated_at": now_iso(),
            }
        )
        upsert_frame(self.conn, "securities", out, ["code"])
        self.conn.commit()
        print(f"[ingest] securities {len(out)} rows")

    def sync_index_members(self, indices: list[str], start: str, end: str) -> None:
        months = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M")
        total = 0
        for idx in indices:
            for month in months:
                s = month.start_time.strftime("%Y%m%d")
                e = month.end_time.strftime("%Y%m%d")
                try:
                    df = self.client.query(
                        "index_weight",
                        {"index_code": idx, "start_date": s, "end_date": e},
                        "index_code,con_code,trade_date,weight",
                    )
                except NoPermission as exc:
                    print(f"[warn] index_weight 无权限: {exc}", file=sys.stderr)
                    return
                if df.empty:
                    continue
                out = pd.DataFrame(
                    {
                        "index_code": df["index_code"],
                        "date": df["trade_date"].map(dashed),
                        "code": df["con_code"].map(to_code),
                        "weight": pd.to_numeric(df["weight"], errors="coerce"),
                    }
                ).drop_duplicates(["index_code", "date", "code"])
                total += upsert_frame(self.conn, "index_member", out,
                                      ["index_code", "date", "code"])
        self.conn.commit()
        print(f"[ingest] index_member {total} rows")

    def build_universe(self, indices: list[str], start: str, end: str) -> list[str]:
        q = (
            "SELECT DISTINCT code FROM index_member WHERE index_code IN (%s)"
            % ",".join("?" for _ in indices)
        )
        codes = [r[0] for r in self.conn.execute(q, indices)]
        if not codes:
            codes = [r[0] for r in self.conn.execute("SELECT code FROM securities WHERE list_status='L'")]
        if not codes:
            return []
        info = {
            row[0]: row[1:]
            for row in self.conn.execute(
                "SELECT code,list_date,delist_date,name FROM securities WHERE code IN (%s)"
                % ",".join("?" for _ in codes),
                codes,
            )
        }
        keep = []
        for code in sorted(codes):
            list_date, delist_date, name = info.get(code, (None, None, ""))
            if list_date and list_date > end:
                continue
            if delist_date and delist_date < start:
                continue
            if any(x in str(name).upper() for x in ("ST", "退")):
                continue
            keep.append(code)
        return keep

    def sync_index_daily(self, codes: list[str], start: str, end: str) -> None:
        for code in dict.fromkeys(codes):
            try:
                df = self.client.query(
                    "index_daily",
                    {"ts_code": code, "start_date": compact(start), "end_date": compact(end)},
                    "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
                )
            except NoPermission:
                return
            except Exception as exc:
                print(f"[warn] index_daily {code}: {exc}", file=sys.stderr)
                continue
            if df.empty:
                continue
            out = pd.DataFrame(
                {
                    "code": to_code(code),
                    "date": df["trade_date"].map(dashed),
                    "open": _num(df, "open"),
                    "high": _num(df, "high"),
                    "low": _num(df, "low"),
                    "close": _num(df, "close"),
                    "pre_close": _num(df, "pre_close"),
                    "pct_chg": _num(df, "pct_chg") / 100.0,
                    "volume": _num(df, "vol") * 100,
                    "amount": _num(df, "amount") * 1000,
                }
            ).drop_duplicates(["code", "date"])
            upsert_frame(self.conn, "index_daily", out, ["code", "date"])
        self.conn.commit()
        print("[ingest] index_daily done")

    def finalize(self, indices: list[str], start: str, end: str) -> None:
        counts = {}
        for table in ("daily", "adj_factor", "daily_basic", "moneyflow", "stk_limit", "fina"):
            counts[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            ("data_summary", json.dumps({"range": [start, end], "indices": indices,
                                         "counts": counts, "updated_at": now_iso()},
                                        ensure_ascii=False)),
        )
        print(f"[ingest] 表行数 {counts}")

    # -- per-code datasets -------------------------------------------------
    def _state(self, dataset: str, code: str) -> tuple[str, str, str] | None:
        row = self.conn.execute(
            "SELECT start_date,end_date,status FROM ingest_state WHERE dataset=? AND code=?",
            (dataset, code),
        ).fetchone()
        return row  # type: ignore[return-value]

    def _set_state(self, dataset: str, code: str, start: str, end: str, rows: int,
                   status: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ingest_state(dataset,code,start_date,end_date,rows,status,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (dataset, code, start, end, rows, status, now_iso()),
        )

    def ingest_dataset(self, dataset: str, code: str, start: str, end: str) -> None:
        delist = self.conn.execute(
            "SELECT delist_date,list_date FROM securities WHERE code=?", (code,)
        ).fetchone()
        effective_end = end
        if delist and delist[0]:
            effective_end = min(end, delist[0])
        if delist and delist[1] and delist[1] > end:
            return

        state = self._state(dataset, code)
        if state and state[2] == "ok" and state[1] and state[1] >= shift_days(effective_end, -7):
            self.client.stats.skipped += 1
            return

        fn: Callable[[str, str, str], int] = getattr(self, f"_ingest_{dataset}")
        rows = fn(code, start, effective_end)
        self._set_state(dataset, code, start, effective_end, rows, "ok")
        self.conn.commit()

    def _ingest_daily(self, code: str, start: str, end: str) -> int:
        ts = to_ts_code(code)
        df = self.client.query(
            "daily",
            {"ts_code": ts, "start_date": compact(start), "end_date": compact(end)},
            "ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
        )
        if df.empty:
            return 0
        out = pd.DataFrame(
            {
                "code": code,
                "date": df["trade_date"].map(dashed),
                "open": _num(df, "open"),
                "high": _num(df, "high"),
                "low": _num(df, "low"),
                "close": _num(df, "close"),
                "pre_close": _num(df, "pre_close"),
                "volume": _num(df, "vol") * 100.0,
                "amount": _num(df, "amount") * 1000.0,
            }
        ).drop_duplicates(["code", "date"])
        return upsert_frame(self.conn, "daily", out, ["code", "date"])

    def _ingest_adj_factor(self, code: str, start: str, end: str) -> int:
        df = self.client.query(
            "adj_factor",
            {"ts_code": to_ts_code(code), "start_date": compact(start), "end_date": compact(end)},
            "ts_code,trade_date,adj_factor",
        )
        if df.empty:
            return 0
        out = pd.DataFrame(
            {"code": code, "date": df["trade_date"].map(dashed),
             "adj_factor": _num(df, "adj_factor")}
        )
        return upsert_frame(self.conn, "adj_factor", out, ["code", "date"])

    def _ingest_daily_basic(self, code: str, start: str, end: str) -> int:
        df = self.client.query(
            "daily_basic",
            {"ts_code": to_ts_code(code), "start_date": compact(start), "end_date": compact(end)},
            "ts_code,trade_date,turnover_rate_f,volume_ratio,pe_ttm,pb,ps_ttm,dv_ttm,"
            "total_share,float_share,free_share,total_mv,circ_mv",
        )
        if df.empty:
            return 0
        out = pd.DataFrame(
            {
                "code": code,
                "date": df["trade_date"].map(dashed),
                "turnover_f": _num(df, "turnover_rate_f") / 100.0,
                "volume_ratio": _num(df, "volume_ratio"),
                "pe_ttm": _num(df, "pe_ttm"),
                "pb": _num(df, "pb"),
                "ps_ttm": _num(df, "ps_ttm"),
                "dv_ttm": _num(df, "dv_ttm") / 100.0,
                "total_share": _num(df, "total_share") * 1e4,
                "float_share": _num(df, "float_share") * 1e4,
                "free_share": _num(df, "free_share") * 1e4,
                "total_mv": _num(df, "total_mv") * 1e4,
                "circ_mv": _num(df, "circ_mv") * 1e4,
            }
        ).drop_duplicates(["code", "date"])
        return upsert_frame(self.conn, "daily_basic", out, ["code", "date"])

    def _ingest_moneyflow(self, code: str, start: str, end: str) -> int:
        df = self.client.query(
            "moneyflow",
            {"ts_code": to_ts_code(code), "start_date": compact(start), "end_date": compact(end)},
            "ts_code,trade_date,buy_elg_amount,sell_elg_amount,buy_lg_amount,"
            "sell_lg_amount,net_mf_amount",
        )
        if df.empty:
            return 0
        out = pd.DataFrame(
            {
                "code": code,
                "date": df["trade_date"].map(dashed),
                "buy_elg": _num(df, "buy_elg_amount") * 1e4,
                "sell_elg": _num(df, "sell_elg_amount") * 1e4,
                "buy_lg": _num(df, "buy_lg_amount") * 1e4,
                "sell_lg": _num(df, "sell_lg_amount") * 1e4,
                "net_mf": _num(df, "net_mf_amount") * 1e4,
            }
        ).drop_duplicates(["code", "date"])
        return upsert_frame(self.conn, "moneyflow", out, ["code", "date"])

    def _ingest_stk_limit(self, code: str, start: str, end: str) -> int:
        df = self.client.query(
            "stk_limit",
            {"ts_code": to_ts_code(code), "start_date": compact(start), "end_date": compact(end)},
            "trade_date,ts_code,up_limit,down_limit",
        )
        if df.empty:
            return 0
        out = pd.DataFrame(
            {"code": code, "date": df["trade_date"].map(dashed),
             "up_limit": _num(df, "up_limit"), "down_limit": _num(df, "down_limit")}
        )
        return upsert_frame(self.conn, "stk_limit", out, ["code", "date"])

    def _ingest_fina(self, code: str, start: str, end: str) -> int:
        fina_start = compact(shift_days(start, -900))
        df = self.client.query(
            "fina_indicator",
            {"ts_code": to_ts_code(code), "start_date": fina_start, "end_date": compact(end)},
            "ts_code,ann_date,end_date,roe,netprofit_yoy,or_yoy,debt_to_assets,"
            "grossprofit_margin,eps,bps,ocfps,q_roe,q_profit_yoy,q_sales_yoy",
        )
        if df.empty:
            return 0
        df = df.dropna(subset=["ann_date", "end_date"])
        out = pd.DataFrame(
            {
                "code": code,
                "ann_date": df["ann_date"].map(dashed),
                "end_date": df["end_date"].map(dashed),
            }
        )
        for col in ("roe", "netprofit_yoy", "or_yoy", "debt_to_assets", "grossprofit_margin",
                    "eps", "bps", "ocfps", "q_roe", "q_profit_yoy", "q_sales_yoy"):
            out[col] = _num(df, col)
        out = out.drop_duplicates(["code", "end_date", "ann_date"], keep="last")
        return upsert_frame(self.conn, "fina", out, ["code", "end_date", "ann_date"])


def ingest(cfg: Config, indices: list[str] | None = None, start: str | None = None,
           end: str | None = None, limit: int | None = None, codes: list[str] | None = None,
           skip: tuple[str, ...] = (), interval: float = 0.13) -> dict[str, Any]:
    ing = Ingestor(cfg, interval=interval)
    return ing.run(indices or list(cfg.get("data.universe_indices", ["000300.SH", "000905.SH"])),
                   start=start or cfg.data_start, end=end or cfg.data_end,
                   limit=limit, codes=codes, skip=skip)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AlphaForge Tushare ingestion")
    parser.add_argument("--config", default=None)
    parser.add_argument("--indices", default=None, help="逗号分隔的指数代码")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--codes", default=None, help="逗号分隔的 6 位代码，用于冒烟测试")
    parser.add_argument("--skip", default="", help="逗号分隔的跳过的数据集")
    parser.add_argument("--interval", type=float, default=0.13)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    ingest(
        cfg,
        indices=args.indices.split(",") if args.indices else None,
        start=args.start,
        end=args.end,
        limit=args.limit,
        codes=args.codes.split(",") if args.codes else None,
        skip=tuple(x for x in args.skip.split(",") if x),
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
