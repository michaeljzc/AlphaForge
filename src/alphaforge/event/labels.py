"""Event labels: forward path, three-tier classification, leakage-safe."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.event.detector import EventConfig


def label_events(panel: Panel, events: pd.DataFrame, cfg: Config | None = None,
                 event_cfg: EventConfig | None = None) -> pd.DataFrame:
    """Compute forward-path labels using only data at/after T0.

    ``label_ret``  : close(T0+60) / close(T0) - 1  (research label)
    ``label_max``  : max(high(T0+1..T0+60)) / close(T0) - 1
    ``label_mdd``  : min(low(T0+1..T0+60)) / close(T0) - 1
    ``entry_ret``  : close(T0+60) / open(T0+1) - 1  (tradeable version)
    """
    cfg = cfg or load_config()
    ec = event_cfg or EventConfig.from_config(cfg)
    if events.empty:
        return events
    close = panel.field("close").astype(np.float64)
    high = panel.field("high").astype(np.float64)
    low = panel.field("low").astype(np.float64)
    open_ = panel.field("open").astype(np.float64)
    sym = {c: i for i, c in enumerate(panel.symbols)}
    T = panel.shape[0]

    out = events.copy()
    lr, lmax, lmdd, eret = [], [], [], []
    for row in out.itertuples(index=False):
        t0 = int(row.t0_idx)
        j = sym[row.code]
        entry = int(row.entry_idx)
        end = min(t0 + ec.label_window, T - 1)
        c0 = close[t0, j]
        if not np.isfinite(c0) or c0 <= 0:
            lr.append(np.nan); lmax.append(np.nan); lmdd.append(np.nan); eret.append(np.nan)
            continue
        hs = high[entry:end + 1, j]
        ls = low[entry:end + 1, j]
        lr.append(float(close[end, j] / c0 - 1) if np.isfinite(close[end, j]) else np.nan)
        lmax.append(float(np.nanmax(hs) / c0 - 1) if len(hs) and np.isfinite(hs).any() else np.nan)
        lmdd.append(float(np.nanmin(ls) / c0 - 1) if len(ls) and np.isfinite(ls).any() else np.nan)
        e0 = open_[entry, j]
        eret.append(float(close[end, j] / e0 - 1) if np.isfinite(e0) and np.isfinite(close[end, j]) else np.nan)
    out["label_ret"] = lr
    out["label_max"] = lmax
    out["label_mdd"] = lmdd
    out["entry_ret"] = eret

    def tier(row: pd.Series) -> str:
        mx, mdd = row["label_max"], row["label_mdd"]
        if pd.isna(mx):
            return "unknown"
        if mx >= ec.strong_return and (pd.isna(mdd) or abs(mdd) <= ec.strong_max_drawdown):
            return "strong"
        if mx >= ec.weak_return:
            return "weak"
        return "negative"

    out["tier"] = out.apply(tier, axis=1)
    out["y_strong"] = (out["tier"] == "strong").astype(int)
    out["y_weak"] = out["tier"].isin(["strong", "weak"]).astype(int)
    return out


def tier_summary(events: pd.DataFrame) -> dict[str, Any]:
    if events.empty:
        return {}
    counts = events["tier"].value_counts().to_dict()
    n = len(events)
    return {
        "n_events": n,
        "tiers": counts,
        "strong_rate": float(counts.get("strong", 0) / n),
        "weak_rate": float(counts.get("weak", 0) / n),
        "negative_rate": float(counts.get("negative", 0) / n),
        "mean_label_ret": float(events["label_ret"].mean()),
        "median_label_ret": float(events["label_ret"].median()),
        "mean_label_max": float(events["label_max"].mean()),
    }
