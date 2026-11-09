"""T0 volume-surge event detection.

An event is a *stock-day* that looks like the start of a launch:

    volume / mean(volume, 20) >= volume_ratio_min
    daily return >= pct_chg_min
    turnover percentile(120) >= turnover_pct_min
    close > mean(close, 20)
    amount >= min_amount, not suspended, not sealed at the up-limit

Events on the same stock within ``cooldown`` trading days are collapsed to the
first occurrence so that one launch is not counted ten times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.expr import Evaluator


@dataclass
class EventConfig:
    lookback: int = 250
    label_window: int = 60
    volume_ratio_min: float = 2.5
    pct_chg_min: float = 0.03
    turnover_pct_min: float = 0.80
    close_above_ma20: bool = True
    min_amount: float = 5_000_000
    exclude_open_limit_up: bool = True
    cooldown: int = 20
    strong_return: float = 2.0
    weak_return: float = 0.6
    strong_max_drawdown: float = 0.5
    cross_section_days: int = 20
    min_events_per_section: int = 5
    hold_days: int = 60
    max_positions: int = 20

    @classmethod
    def from_config(cls, cfg: Config) -> "EventConfig":
        e = cls()
        node = cfg.get("event", {}) or {}
        for key, value in node.items():
            if hasattr(e, key) and value is not None:
                setattr(e, key, value)
        return e


def detect_events(panel: Panel, cfg: Config | None = None,
                  evaluator: Evaluator | None = None,
                  event_cfg: EventConfig | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    ec = event_cfg or EventConfig.from_config(cfg)
    ev = evaluator or Evaluator(panel, mask="universe")

    vol_ratio = ev.eval("volume/(ts_mean(volume, 20)+1e-9)")
    turn_rank = ev.eval("ts_rank(turnover_f, 120)")
    ma20 = ev.eval("ts_mean(close, 20)")
    ret = panel.field("ret")
    amount = panel.field("amount")
    open_ = panel.field("open")
    up = panel.field("up_limit")
    suspended = panel.mask("suspended")
    universe = panel.mask("universe")

    cond = (
        universe
        & np.isfinite(vol_ratio)
        & (vol_ratio >= ec.volume_ratio_min)
        & np.isfinite(ret) & (ret >= ec.pct_chg_min)
        & np.isfinite(turn_rank) & (turn_rank >= ec.turnover_pct_min)
        & np.isfinite(amount) & (amount >= ec.min_amount)
        & ~suspended
    )
    if ec.close_above_ma20:
        cond &= np.isfinite(ma20) & (panel.field("close") > ma20)
    if ec.exclude_open_limit_up:
        cond &= ~(np.isfinite(up) & np.isfinite(open_) & (open_ >= up - 0.005))

    T, N = panel.shape
    rows: list[dict[str, Any]] = []
    for j in range(N):
        idxs = np.flatnonzero(cond[:, j])
        last = -10**9
        for t in idxs:
            if t - last < ec.cooldown:
                continue
            if t + 1 >= T:
                continue
            last = t
            entry = t + 1
            exit_idx = min(entry + ec.hold_days, T - 1)
            rows.append({
                "t0_idx": int(t),
                "t0_date": panel.date_strs[t],
                "code": panel.symbols[j],
                "entry_idx": int(entry),
                "exit_idx": int(exit_idx),
                "vol_ratio": float(vol_ratio[t, j]),
                "pct_chg": float(ret[t, j]),
                "turnover_pct": float(turn_rank[t, j]),
                "amount": float(amount[t, j]),
                "close": float(panel.field("close")[t, j]),
                "log_mv": float(panel.field("log_mv")[t, j]) if np.isfinite(panel.field("log_mv")[t, j]) else np.nan,
                "entry_tradable": bool(panel.mask("tradable")[entry, j]),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["t0_idx", "code"]).reset_index(drop=True)
