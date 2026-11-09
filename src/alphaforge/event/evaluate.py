"""Event-cross-section evaluation and event-driven portfolio backtest."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.event.dataset import EventDataset
from alphaforge.evaluate.core import rank_pct, _spearman_1d


def _section_ic(df: pd.DataFrame, feature: str, label: str,
                min_events: int) -> pd.Series:
    vals = []
    idx = []
    for section, g in df.groupby("section"):
        g = g[[feature, label]].dropna()
        if len(g) < min_events:
            continue
        vals.append(_spearman_1d(g[feature].to_numpy(), g[label].to_numpy()))
        idx.append(section)
    return pd.Series(vals, index=idx).dropna()


def event_ic(dataset: EventDataset, features: Sequence[str] | None = None,
             label: str = "label_ret", min_events: int = 5) -> pd.DataFrame:
    df = dataset.events
    features = list(features or dataset.features)
    rows = []
    for f in features:
        if f not in df.columns:
            continue
        ic = _section_ic(df, f, label, min_events)
        if len(ic) == 0:
            continue
        mean = float(ic.mean())
        std = float(ic.std(ddof=1)) if len(ic) > 1 else float("nan")
        icir = mean / std if std and math.isfinite(std) else float("nan")
        pos = float((ic > 0).mean())
        rows.append({
            "feature": f, "ic": mean, "icir": icir, "n_sections": len(ic),
            "hit_rate": max(pos, 1 - pos), "positive_rate": pos,
            "t_stat": icir * math.sqrt(len(ic)) if math.isfinite(icir) else float("nan"),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("ic", key=lambda s: s.abs(), ascending=False) if not out.empty else out


def event_precision(dataset: EventDataset, feature: str,
                    top_frac: float = 0.2, ascending: bool = False) -> dict[str, Any]:
    df = dataset.events[[feature, "y_strong", "y_weak", "tier"]].dropna()
    if len(df) < 20:
        return {}
    base_strong = float(df["y_strong"].mean())
    base_weak = float(df["y_weak"].mean())
    n = max(1, int(len(df) * top_frac))
    if ascending:
        top = df.nsmallest(n, feature)
        bottom = df.nlargest(n, feature)
    else:
        top = df.nlargest(n, feature)
        bottom = df.nsmallest(n, feature)
    out = {
        "feature": feature,
        "n": len(df),
        "base_strong_rate": base_strong,
        "base_weak_rate": base_weak,
        "top_strong_rate": float(top["y_strong"].mean()),
        "top_weak_rate": float(top["y_weak"].mean()),
        "bottom_strong_rate": float(bottom["y_strong"].mean()),
        "bottom_weak_rate": float(bottom["y_weak"].mean()),
        "lift": float(top["y_strong"].mean() / base_strong) if base_strong > 0 else float("nan"),
        "recall_strong": float(top["y_strong"].sum() / max(df["y_strong"].sum(), 1)),
    }
    return out


def event_backtest(dataset: EventDataset, panel: Panel, cfg: Config | None = None,
                   feature: str | None = None, top_frac: float | None = None,
                   max_positions: int | None = None,
                   ascending: bool = False) -> dict[str, Any]:
    """Equal-slot event portfolio: enter T0+1 open, exit T0+1+hold.

    If ``feature`` is given, only the top ``top_frac`` events by that score are
    traded; otherwise all detected events are traded (the event universe
    benchmark).
    """
    cfg = cfg or load_config()
    ec = dataset.config
    hold = int(ec.get("hold_days", 60))
    max_pos = int(max_positions or ec.get("max_positions", 20))
    slip = float(cfg.get("backtest.slippage_bps", 5)) / 1e4
    comm = float(cfg.get("backtest.commission_bps", 3)) / 1e4
    stamp = float(cfg.get("backtest.stamp_duty_bps", 5)) / 1e4
    initial = float(cfg.get("backtest.initial_cash", 10_000_000))
    lot = int(cfg.get("backtest.lot_size", 100))

    df = dataset.events.copy()
    if feature and top_frac:
        df = df.dropna(subset=[feature])
        n = max(1, int(len(df) * top_frac))
        df = df.nsmallest(n, feature) if ascending else df.nlargest(n, feature)
    df = df[df["entry_tradable"]].sort_values("entry_idx")
    if df.empty:
        return {"error": "没有可交易事件"}

    T = panel.shape[0]
    sym = {c: i for i, c in enumerate(panel.symbols)}
    open_ = panel.field("open")
    close = panel.field("close")
    tradable = panel.mask("tradable")
    # a position must be sellable even after it leaves the index: use the
    # exchange rules (suspension / limit-down) rather than the universe mask
    sellable = ~panel.mask("suspended") & ~panel.mask("limit_down")

    cash = initial
    positions: dict[str, dict[str, Any]] = {}
    equity = np.zeros(T)
    equity[:] = np.nan
    trades = []
    by_entry: dict[int, list[Any]] = {}
    for row in df.itertuples(index=False):
        by_entry.setdefault(int(row.entry_idx), []).append(row)

    start = int(df["entry_idx"].min())
    for d in range(start, T):
        # exits
        for code, pos in list(positions.items()):
            j = pos["j"]
            if d >= pos["exit_planned"]:
                px = float(close[d, j])
                if not np.isfinite(px) or not sellable[d, j]:
                    if d - pos["exit_planned"] > 20:
                        px = float(close[d, j]) if np.isfinite(close[d, j]) else pos["last_price"]
                        if np.isfinite(px):
                            value = pos["shares"] * px * (1 - slip)
                            fee = value * (comm + stamp)
                            cash += value - fee
                            trades.append({"code": code, "entry_date": pos["entry_date"],
                                           "exit_date": panel.date_strs[d], "ret": value / (pos["cost"]) - 1,
                                           "forced": True})
                            del positions[code]
                    continue
                value = pos["shares"] * px * (1 - slip)
                fee = value * (comm + stamp)
                cash += value - fee
                trades.append({"code": code, "entry_date": pos["entry_date"],
                               "exit_date": panel.date_strs[d], "ret": value / pos["cost"] - 1,
                               "forced": False})
                del positions[code]
            else:
                px = float(close[d, j])
                if np.isfinite(px):
                    pos["last_price"] = px

        # entries
        for row in by_entry.get(d, []):
            j = sym.get(row.code)
            if j is None or not tradable[d, j]:
                continue
            px = float(open_[d, j])
            if not np.isfinite(px) or px <= 0:
                continue
            slots = max_pos - len(positions)
            if slots <= 0:
                break
            equity_now = cash + sum(p["shares"] * p["last_price"] for p in positions.values())
            budget = min(equity_now / max_pos, cash * 0.95 / max(1, slots))
            if budget < 1000:
                break
            shares = int(budget / (px * (1 + slip)) // lot) * lot
            if shares < lot:
                continue
            cost = shares * px * (1 + slip)
            fee = max(cost * comm, 5.0)
            if cost + fee > cash:
                continue
            cash -= cost + fee
            positions[row.code] = {
                "j": j, "shares": shares, "cost": cost + fee, "last_price": px,
                "entry_date": panel.date_strs[d],
                "exit_planned": min(d + hold, T - 1),
            }
        eq = cash + sum(p["shares"] * p["last_price"] for p in positions.values())
        equity[d] = eq

    valid = np.isfinite(equity)
    idx = np.flatnonzero(valid)
    if len(idx) == 0:
        return {"error": "无法估值"}
    eq = pd.Series(equity[idx], index=pd.DatetimeIndex(panel.dates[idx]))
    rets = eq.pct_change().fillna(0.0)
    years = max(len(eq) / 252, 1e-9)
    total = float(eq.iloc[-1] / eq.iloc[0] - 1)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1)
    vol = float(rets.std() * math.sqrt(252))
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else float("nan")
    cum = (1 + rets).cumprod()
    dd = float((cum / cum.cummax() - 1).min())
    tr = pd.DataFrame(trades)
    return {
        "n_events": int(len(df)),
        "n_trades": int(len(tr)),
        "start": str(eq.index[0].date()), "end": str(eq.index[-1].date()),
        "initial": initial, "final": float(eq.iloc[-1]),
        "total_return": total, "cagr": cagr, "volatility": vol, "sharpe": sharpe,
        "max_drawdown": dd,
        "win_rate": float((tr["ret"] > 0).mean()) if len(tr) else float("nan"),
        "avg_trade_ret": float(tr["ret"].mean()) if len(tr) else float("nan"),
        "median_trade_ret": float(tr["ret"].median()) if len(tr) else float("nan"),
        "profit_factor": float(tr.loc[tr["ret"] > 0, "ret"].sum() /
                               abs(tr.loc[tr["ret"] < 0, "ret"].sum()))
        if len(tr) and (tr["ret"] < 0).any() else float("nan"),
        "equity_dates": [str(d.date()) for d in eq.index],
        "equity": [float(x) for x in eq.to_numpy()],
        "trades": tr.to_dict(orient="records") if len(tr) else [],
    }
