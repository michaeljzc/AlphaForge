"""Panel data layer.

The panel is the unit of computation for the whole platform: a dense
``(T dates x N symbols)`` float32 cube plus masks.  Everything (factor
expressions, IC, GP mining, backtests) consumes this object so that the
data alignment / PIT / tradability rules are enforced in exactly one place.

Conventions
-----------
prices   : forward-adjusted (qfq) in CNY, so returns are split/dividend safe
volume   : shares (raw)
amount   : CNY (raw)
masks    : uint8 0/1 arrays, same shape as fields
PIT      : financial fields are as-of ``ann_date``, never report period
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.schema import DDL
from alphaforge.utils import Timer, connect, dashed, query_df, write_json

DAILY_COLS = ["open", "high", "low", "close", "pre_close", "volume", "amount"]
BASIC_COLS = [
    "turnover_f", "volume_ratio", "pe_ttm", "pb", "ps_ttm", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv", "circ_mv",
]
FLOW_COLS = ["buy_elg", "sell_elg", "buy_lg", "sell_lg", "net_mf"]
LIMIT_COLS = ["up_limit", "down_limit"]
PIT_COLS = [
    "roe", "netprofit_yoy", "or_yoy", "debt_to_assets", "grossprofit_margin",
    "eps", "bps", "ocfps", "q_roe", "q_profit_yoy", "q_sales_yoy",
]

ALIASES = {
    "vol": "volume",
    "turnover": "turnover_f",
    "turnover_rate": "turnover_f",
    "turnover_rate_f": "turnover_f",
    "mv": "circ_mv",
    "logmv": "log_mv",
    "logmv_total": "log_total_mv",
    "main": "main_net",
    "main_ratio": "main_net_ratio",
    "net_mf_ratio": "main_net_ratio",
    "returns": "ret",
    "pct_chg": "ret",
    "chg": "ret",
    "adjclose": "close",
    "adj_close": "close",
    "adjopen": "open",
    "adj_open": "open",
    "adjhigh": "high",
    "adj_high": "high",
    "adjlow": "low",
    "adj_low": "low",
    "adjvwap": "vwap",
    "limit_up": "limit_up_flag",
    "limit_down": "limit_down_flag",
    "ep": "earnings_yield",
    "bp": "book_to_price",
    "sp": "sales_to_price",
    "dy": "dividend_yield",
    "st": "is_st",
    "listed": "listed_days",
    "free_turnover": "free_turnover",
    "ln_mv": "log_mv",
}


@dataclass
class Panel:
    dates: np.ndarray                 # datetime64[D]
    symbols: list[str]
    data: dict[str, np.ndarray]       # float32 (T, N)
    industry_id: np.ndarray           # int16 (N,)
    industry_names: list[str]
    masks: dict[str, np.ndarray] = field(default_factory=dict)  # uint8 (T, N)
    meta: dict[str, Any] = field(default_factory=dict)

    # -- basics ------------------------------------------------------------
    @property
    def shape(self) -> tuple[int, int]:
        return len(self.dates), len(self.symbols)

    @property
    def date_strs(self) -> list[str]:
        return [str(d) for d in self.dates]

    def date_index(self, value: str, strict: bool = True) -> int:
        d = np.datetime64(dashed(value), "D")
        idx = int(np.searchsorted(self.dates, d))
        if idx >= len(self.dates) or self.dates[idx] != d:
            if strict:
                raise KeyError(f"日期 {value} 不在面板日历内")
            return min(max(idx - 1, 0), len(self.dates) - 1)
        return idx

    def symbol_index(self, code: str) -> int:
        try:
            return self.symbols.index(code)
        except ValueError as exc:
            raise KeyError(f"代码 {code} 不在面板内") from exc

    # -- fields ------------------------------------------------------------
    def has(self, name: str) -> bool:
        return self._norm(name) in self.data

    def _norm(self, name: str) -> str:
        key = name.strip().lower()
        key = ALIASES.get(key, key)
        return "$" + key if key.startswith("$") else key

    def field(self, name: str) -> np.ndarray:
        key = self._norm(name)
        if key not in self.data:
            raise KeyError(f"未知字段 {name}（可用字段: {', '.join(sorted(self.data))}）")
        return self.data[key]

    def mask(self, name: str) -> np.ndarray:
        key = name.strip().lower()
        if key not in self.masks:
            raise KeyError(f"未知掩码 {name}")
        return self.masks[key].astype(bool)

    def fields(self) -> list[str]:
        return sorted(self.data)

    # -- slicing -----------------------------------------------------------
    def slice(self, start: str | None = None, end: str | None = None,
              symbols: Sequence[str] | None = None) -> "Panel":
        i0, i1 = 0, len(self.dates)
        if start is not None:
            i0 = int(np.searchsorted(self.dates, np.datetime64(dashed(start), "D")))
        if end is not None:
            i1 = int(np.searchsorted(self.dates, np.datetime64(dashed(end), "D"), side="right"))
        if symbols is None:
            col_idx = np.arange(len(self.symbols))
        else:
            wanted = set(symbols)
            col_idx = np.array([i for i, s in enumerate(self.symbols) if s in wanted], dtype=int)
        data = {k: v[i0:i1][:, col_idx] for k, v in self.data.items()}
        masks = {k: v[i0:i1][:, col_idx] for k, v in self.masks.items()}
        return Panel(
            dates=self.dates[i0:i1].copy(),
            symbols=[self.symbols[i] for i in col_idx],
            data=data,
            industry_id=self.industry_id[col_idx].copy(),
            industry_names=self.industry_names,
            masks=masks,
            meta=dict(self.meta),
        )

    def date_mask(self, start: str | None = None, end: str | None = None) -> np.ndarray:
        mask = np.ones(len(self.dates), dtype=bool)
        if start is not None:
            mask &= self.dates >= np.datetime64(dashed(start), "D")
        if end is not None:
            mask &= self.dates <= np.datetime64(dashed(end), "D")
        return mask

    # -- derived helpers ---------------------------------------------------
    def frame(self, name: str) -> pd.DataFrame:
        return pd.DataFrame(self.field(name), index=pd.DatetimeIndex(self.dates),
                            columns=self.symbols)

    def mask_frame(self, name: str) -> pd.DataFrame:
        return pd.DataFrame(self.mask(name).astype(float), index=pd.DatetimeIndex(self.dates),
                            columns=self.symbols)

    def forward_return(self, horizon: int = 5, price: str = "close",
                       lag: int = 0) -> np.ndarray:
        """Return from t+lag to t+lag+horizon (signal at t close)."""
        p = self.field(price).astype(np.float64)
        out = np.full_like(p, np.nan)
        if horizon <= 0:
            raise ValueError("horizon 必须为正")
        T = p.shape[0]
        src = p[lag: T - horizon]
        dst = p[lag + horizon: T]
        valid = np.isfinite(src) & np.isfinite(dst)
        block = np.full_like(src, np.nan)
        block[valid] = dst[valid] / src[valid] - 1.0
        out[: block.shape[0]] = block
        return out

    def forward_path(self, horizon: int, lag: int = 1) -> dict[str, np.ndarray]:
        """Forward max/min/terminal path stats used by event labels.

        All arrays are aligned so index t refers to an event at t.
        """
        close = self.field("close").astype(np.float64)
        high = self.field("high").astype(np.float64)
        low = self.field("low").astype(np.float64)
        T, N = close.shape
        fmax = np.full((T, N), np.nan)
        fmin = np.full((T, N), np.nan)
        fend = np.full((T, N), np.nan)
        for t in range(T - horizon):
            t0 = t + lag
            t1 = min(t0 + horizon, T)
            c0 = close[t]
            block_h = high[t0:t1]
            block_l = low[t0:t1]
            with np.errstate(all="ignore"):
                fmax[t] = np.nanmax(block_h, axis=0) / c0 - 1.0
                fmin[t] = np.nanmin(block_l, axis=0) / c0 - 1.0
                fend[t] = close[t1 - 1] / c0 - 1.0
        return {"max_ret": fmax, "min_ret": fmin, "end_ret": fend}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "dates": self.dates.astype("datetime64[D]"),
            "symbols": np.array(self.symbols, dtype=object),
            "industry_id": self.industry_id,
            "industry_names": np.array(self.industry_names, dtype=object),
            "meta": np.array(json.dumps(self.meta, ensure_ascii=False, default=str)),
        }
        for k, v in self.data.items():
            arrays[f"f__{k}"] = v
        for k, v in self.masks.items():
            arrays[f"m__{k}"] = v
        np.savez(p, **arrays)

    @classmethod
    def load(cls, path: str | Path) -> "Panel":
        doc = np.load(Path(path), allow_pickle=True)
        data = {k[3:]: doc[k] for k in doc.files if k.startswith("f__")}
        masks = {k[3:]: doc[k] for k in doc.files if k.startswith("m__")}
        return cls(
            dates=doc["dates"].astype("datetime64[D]"),
            symbols=[str(s) for s in doc["symbols"]],
            data=data,
            industry_id=doc["industry_id"],
            industry_names=[str(s) for s in doc["industry_names"]],
            masks=masks,
            meta=json.loads(str(doc["meta"])),
        )


# --------------------------------------------------------------------------
# construction
# --------------------------------------------------------------------------
class PanelStore:
    """Builds a :class:`Panel` from the SQLite market lake, with caching."""

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.conn = connect(self.cfg.paths.market_db, readonly=True)

    # -- public ------------------------------------------------------------
    def build(self, start: str | None = None, end: str | None = None,
              use_cache: bool = True, cache_tag: str = "main") -> Panel:
        start = start or self.cfg.data_start
        end = end or self.cfg.data_end
        cache = self.cfg.paths.cache / f"panel_{cache_tag}_{dashed(start).replace('-', '')}_{dashed(end).replace('-', '')}.npz"
        db_mtime = Path(self.cfg.paths.market_db).stat().st_mtime
        meta_path = cache.with_suffix(".json")
        if use_cache and cache.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if meta.get("db_mtime") == db_mtime:
                t0 = time.time()
                panel = Panel.load(cache)
                print(f"[panel] cache hit {cache.name} {panel.shape} ({time.time()-t0:.1f}s)")
                return panel

        with Timer("panel build"):
            panel = self._build(dashed(start), dashed(end))
        if use_cache:
            with Timer("panel cache write"):
                panel.save(cache)
                write_json(meta_path, {"db_mtime": db_mtime, "shape": list(panel.shape),
                                       "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        return panel

    # -- internals ---------------------------------------------------------
    def _build(self, start: str, end: str) -> Panel:
        t0 = time.time()
        cal = self._calendar(start, end)
        codes = self._codes(start, end)
        print(f"[panel] {len(cal)} dates x {len(codes)} symbols")
        dates = np.array([np.datetime64(d, "D") for d in cal])
        data: dict[str, np.ndarray] = {}

        # ---- prices ------------------------------------------------------
        daily = self._load("daily", DAILY_COLS, cal, codes)
        raw_open, raw_high, raw_low, raw_close = (
            daily["open"], daily["high"], daily["low"], daily["close"])
        raw_pre_close = daily["pre_close"]
        raw_vol, raw_amount = daily["volume"], daily["amount"]
        raw_vwap = np.where(raw_vol > 0, raw_amount / np.maximum(raw_vol, 1e-12), np.nan)

        adj = self._load("adj_factor", ["adj_factor"], cal, codes)["adj_factor"]
        adj_ff = _ffill(adj)
        # normalise to the last observation so prices are comparable to today's CNY
        last_adj = _last_valid(adj_ff)
        ratio = adj_ff / np.where(np.isfinite(last_adj), last_adj, np.nan)
        ratio = np.where(np.isfinite(ratio) & (ratio > 0), ratio, np.nan)

        close = raw_close * ratio
        open_ = raw_open * ratio
        high = raw_high * ratio
        low = raw_low * ratio
        vwap = raw_vwap * ratio
        data.update(
            close=close.astype(np.float32), open=open_.astype(np.float32),
            high=high.astype(np.float32), low=low.astype(np.float32),
            vwap=np.where(np.isfinite(vwap), vwap, np.nan).astype(np.float32),
            volume=raw_vol.astype(np.float32), amount=raw_amount.astype(np.float32),
            close_raw=raw_close.astype(np.float32),
            open_raw=raw_open.astype(np.float32),
            high_raw=raw_high.astype(np.float32),
            low_raw=raw_low.astype(np.float32),
            pre_close_raw=raw_pre_close.astype(np.float32),
            adj_factor=adj.astype(np.float32),
        )
        prev_close = np.full_like(close, np.nan)
        prev_close[1:] = close[:-1]
        data["pre_close"] = prev_close.astype(np.float32)
        data["ret"] = np.where(np.isfinite(prev_close) & (prev_close > 0),
                               close / prev_close - 1.0, np.nan).astype(np.float32)
        data["log_ret"] = np.log1p(data["ret"]).astype(np.float32)

        # ---- daily basic -------------------------------------------------
        basic = self._load("daily_basic", BASIC_COLS, cal, codes)
        for col in BASIC_COLS:
            data[col] = basic[col]
        circ_mv = basic["circ_mv"]
        total_mv = basic["total_mv"]
        data["log_mv"] = np.where(circ_mv > 0, np.log(circ_mv), np.nan).astype(np.float32)
        data["log_total_mv"] = np.where(total_mv > 0, np.log(total_mv), np.nan).astype(np.float32)
        data["earnings_yield"] = np.where(basic["pe_ttm"] != 0, 1.0 / basic["pe_ttm"], np.nan).astype(np.float32)
        data["book_to_price"] = np.where(basic["pb"] != 0, 1.0 / basic["pb"], np.nan).astype(np.float32)
        data["sales_to_price"] = np.where(basic["ps_ttm"] != 0, 1.0 / basic["ps_ttm"], np.nan).astype(np.float32)
        data["dividend_yield"] = basic["dv_ttm"]
        free_share = np.where(basic["free_share"] > 0, basic["free_share"], np.nan)
        data["free_turnover"] = (raw_vol / free_share).astype(np.float32)

        # ---- money flow --------------------------------------------------
        flow = self._load("moneyflow", FLOW_COLS, cal, codes)
        main_net = ((flow["buy_elg"] + flow["buy_lg"]) - (flow["sell_elg"] + flow["sell_lg"]))
        data["main_net"] = main_net.astype(np.float32)
        data["main_net_ratio"] = np.where(raw_amount > 0, main_net / raw_amount, np.nan).astype(np.float32)
        data["net_mf"] = flow["net_mf"]
        data["net_mf_ratio"] = np.where(raw_amount > 0, flow["net_mf"] / raw_amount, np.nan).astype(np.float32)
        data["buy_elg"] = flow["buy_elg"]
        data["sell_elg"] = flow["sell_elg"]
        data["buy_lg"] = flow["buy_lg"]
        data["sell_lg"] = flow["sell_lg"]

        # ---- limits ------------------------------------------------------
        lim = self._load("stk_limit", LIMIT_COLS, cal, codes)
        up, down = lim["up_limit"], lim["down_limit"]
        data["up_limit"] = up
        data["down_limit"] = down
        valid_up = np.isfinite(up) & np.isfinite(raw_close)
        limit_up_flag = valid_up & (raw_close >= up - 0.005)
        limit_down_flag = np.isfinite(down) & np.isfinite(raw_close) & (raw_close <= down + 0.005)
        data["limit_pct"] = np.where(
            valid_up & np.isfinite(raw_pre_close) & (raw_pre_close > 0),
            up / np.maximum(raw_pre_close, 1e-12) - 1, np.nan,
        ).astype(np.float32)

        # ---- PIT fundamentals -------------------------------------------
        pit = self._load_pit(PIT_COLS, cal, codes)
        for col in PIT_COLS:
            data[col] = pit[col]

        # ---- securities / industry / listing ----------------------------
        sec = query_df(self.conn, "SELECT code,name,industry,board,list_date,is_st FROM securities")
        sec = sec[sec["code"].isin(codes)].set_index("code").reindex(codes)
        industries = sec["industry"].fillna("Unknown").astype(str).tolist()
        uniq = sorted(set(industries))
        ind_map = {name: i for i, name in enumerate(uniq)}
        industry_id = np.array([ind_map[x] for x in industries], dtype=np.int16)
        list_dates = sec["list_date"].tolist()
        boards = sec["board"].fillna("MAIN").astype(str).tolist()
        st_const = sec["is_st"].fillna(0).to_numpy(dtype=np.uint8)

        cal_str = np.array(cal, dtype="datetime64[D]")
        listed_days = np.zeros((len(cal), len(codes)), dtype=np.float32)
        for j, ld in enumerate(list_dates):
            if ld is None or (isinstance(ld, float) and math.isnan(ld)):
                start_idx = 0
            else:
                start_idx = int(np.searchsorted(cal_str, np.datetime64(ld, "D")))
            days = np.arange(len(cal)) - start_idx + 1
            listed_days[:, j] = np.clip(days, 0, None)
        data["listed_days"] = listed_days.astype(np.float32)

        suspended = ~np.isfinite(raw_close) | (raw_vol <= 0)
        data["suspended"] = suspended.astype(np.float32)
        # ST proxy: main-board 5% limit band, excluding the first 10 listed days
        st_proxy = (
            (np.asarray(boards)[None, :] == "MAIN")
            & (data["limit_pct"] > 0.02) & (data["limit_pct"] < 0.08)
            & (listed_days > 10)
        )
        data["is_st"] = st_proxy.astype(np.float32)

        # ---- universe & tradability masks -------------------------------
        member = self._index_members(cal, codes)
        min_list = int(self.cfg.get("data.min_list_days", 60))
        min_price = float(self.cfg.get("data.min_price", 1.0))
        min_amount = float(self.cfg.get("data.min_amount", 5_000_000))
        good = (
            member
            & np.isfinite(raw_close)
            & (raw_close >= min_price)
            & (raw_amount >= min_amount)
            & (listed_days >= min_list)
            & ~suspended
            & ~st_proxy
        )
        tradable = good & ~limit_up_flag
        sellable = good & ~limit_down_flag
        data["limit_up_flag"] = limit_up_flag.astype(np.float32)
        data["limit_down_flag"] = limit_down_flag.astype(np.float32)
        import warnings as _warnings
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", RuntimeWarning)
            mkt = np.nanmean(np.where(good, data["ret"], np.nan), axis=1)
        data["mkt_ret"] = np.broadcast_to(mkt[:, None], (len(cal), len(codes))).astype(np.float32)
        masks = {
            "universe": good.astype(np.uint8),
            "tradable": tradable.astype(np.uint8),
            "sellable": sellable.astype(np.uint8),
            "index_member": member.astype(np.uint8),
            "suspended": suspended.astype(np.uint8),
            "limit_up": limit_up_flag.astype(np.uint8),
            "limit_down": limit_down_flag.astype(np.uint8),
        }
        meta = {
            "start": cal[0], "end": cal[-1], "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "n_dates": len(cal), "n_symbols": len(codes), "build_sec": round(time.time() - t0, 1),
        }
        print(f"[panel] built in {time.time()-t0:.1f}s")
        return Panel(dates=dates, symbols=codes, data=data, industry_id=industry_id,
                     industry_names=uniq, masks=masks, meta=meta)

    # -- sql helpers -------------------------------------------------------
    def _calendar(self, start: str, end: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT date FROM calendar WHERE is_open=1 AND date BETWEEN ? AND ? ORDER BY date",
            (start, end),
        ).fetchall()
        cal = [r[0] for r in rows]
        if not cal:
            raise RuntimeError("交易日历为空，请先执行 ingest")
        return cal

    def _codes(self, start: str, end: str) -> list[str]:
        idx = self.cfg.get("data.universe_indices", ["000300.SH", "000905.SH"])
        q = (
            "SELECT DISTINCT code FROM index_member WHERE index_code IN (%s)"
            % ",".join("?" for _ in idx)
        )
        codes = {r[0] for r in self.conn.execute(q, idx)}
        have = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT code FROM daily WHERE date BETWEEN ? AND ?", (start, end))}
        codes = sorted(codes & have) if codes else sorted(have)
        if not codes:
            raise RuntimeError("股票池为空，请先执行 ingest")
        return codes

    def _load(self, table: str, cols: list[str], cal: list[str],
              codes: list[str]) -> dict[str, np.ndarray]:
        df = query_df(self.conn, f"SELECT code,date,{','.join(cols)} FROM {table}")
        if df.empty:
            return {c: np.full((len(cal), len(codes)), np.nan, dtype=np.float32) for c in cols}
        df = df.drop_duplicates(["code", "date"])
        wide = df.set_index(["code", "date"])[cols].unstack("date")
        out: dict[str, np.ndarray] = {}
        for c in cols:
            sub = wide[c] if isinstance(wide.columns, pd.MultiIndex) else wide
            arr = sub.reindex(index=codes, columns=cal)
            out[c] = np.ascontiguousarray(arr.to_numpy(dtype=np.float32).T)
        return out

    def _load_pit(self, cols: list[str], cal: list[str],
                  codes: list[str]) -> dict[str, np.ndarray]:
        df = query_df(self.conn, f"SELECT code,ann_date,end_date,{','.join(cols)} FROM fina")
        T, N = len(cal), len(codes)
        out = {c: np.full((T, N), np.nan, dtype=np.float32) for c in cols}
        if df.empty:
            return out
        cal_np = np.array(cal, dtype="datetime64[D]")
        code_pos = {c: i for i, c in enumerate(codes)}
        df = df[df["code"].isin(code_pos)]
        for code, g in df.groupby("code", sort=False):
            j = code_pos[code]
            g = g.sort_values(["ann_date", "end_date"], kind="mergesort")
            known: dict[str, Any] = {}
            event_dates: list[str] = []
            event_rows: list[dict[str, Any]] = []
            for ann_date, block in g.groupby("ann_date", sort=True):
                for rec in block.to_dict("records"):
                    known[rec["end_date"]] = rec
                latest_end = max(known)
                event_dates.append(str(ann_date))
                event_rows.append(known[latest_end])
            if not event_dates:
                continue
            ann_np = np.array(event_dates, dtype="datetime64[D]")
            positions = np.searchsorted(ann_np, cal_np, side="right") - 1
            valid = positions >= 0
            for c in cols:
                vals = np.array([_safe_float(r.get(c)) for r in event_rows], dtype=np.float32)
                col = np.full(T, np.nan, dtype=np.float32)
                col[valid] = vals[positions[valid]]
                out[c][:, j] = col
        return out

    def _index_members(self, cal: list[str], codes: list[str]) -> np.ndarray:
        df = query_df(self.conn, "SELECT index_code,date,code FROM index_member")
        T, N = len(cal), len(codes)
        if df.empty:
            return np.ones((T, N), dtype=bool)
        code_pos = {c: i for i, c in enumerate(codes)}
        df = df[df["code"].isin(code_pos)]
        member = np.zeros((T, N), dtype=bool)
        for idx_code, g in df.groupby("index_code"):
            dates = sorted(g["date"].unique())
            snap = np.zeros((len(dates), N), dtype=bool)
            dpos = {d: i for i, d in enumerate(dates)}
            for d, c in zip(g["date"], g["code"]):
                snap[dpos[d], code_pos[c]] = True
            # as-of align snapshots to calendar, then forward fill
            date_np = np.array(dates, dtype="datetime64[D]")
            cal_np = np.array(cal, dtype="datetime64[D]")
            pos = np.searchsorted(date_np, cal_np, side="right") - 1
            valid = pos >= 0
            block = np.zeros((T, N), dtype=bool)
            block[valid] = snap[pos[valid]]
            member |= block
        return member

    def close(self) -> None:
        self.conn.close()


def _safe_float(value: Any) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ffill(arr: np.ndarray) -> np.ndarray:
    out = arr.astype(np.float64, copy=True)
    T = out.shape[0]
    for t in range(1, T):
        mask = ~np.isfinite(out[t]) & np.isfinite(out[t - 1])
        out[t, mask] = out[t - 1, mask]
    return out


def _last_valid(arr: np.ndarray) -> np.ndarray:
    T, N = arr.shape
    last = np.full(N, np.nan)
    for t in range(T):
        valid = np.isfinite(arr[t])
        last[valid] = arr[t, valid]
    return last


def load_panel(cfg: Config | None = None, start: str | None = None,
               end: str | None = None, use_cache: bool = True) -> Panel:
    store = PanelStore(cfg)
    try:
        return store.build(start=start, end=end, use_cache=use_cache)
    finally:
        store.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build the AlphaForge panel cache")
    ap.add_argument("--config", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    p = load_panel(cfg, args.start, args.end, use_cache=not args.no_cache)
    print("shape:", p.shape)
    print("fields:", ", ".join(p.fields()))
    print("masks:", ", ".join(p.masks))
    print("date range:", p.dates[0], p.dates[-1])
