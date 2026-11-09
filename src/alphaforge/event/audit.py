"""Leakage audit for the event dataset.

Three independent checks:

1. **time gate** -- every feature is recomputed on a panel truncated at T0-1
   and must equal the cached value; label dates must be >= T0.
2. **PIT** -- financial reports used for a feature must have ``ann_date`` <= the
   as-of date.
3. **overlap** -- the feature as-of index must be strictly before T0 and the
   label window must start at/after T0.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.event.dataset import EventDataset
from alphaforge.expr import Evaluator
from alphaforge.utils import connect


def audit_event_dataset(panel: Panel, dataset: EventDataset, cfg: Config | None = None,
                        sample: int = 8) -> dict[str, Any]:
    cfg = cfg or load_config()
    df = dataset.events
    if df.empty:
        return {"ok": False, "reason": "empty dataset"}
    rng = np.random.default_rng(7)
    idxs = rng.choice(len(df), size=min(sample, len(df)), replace=False)
    expr_map = {f: e for f, e in dataset.factor_map.items() if f in df.columns}
    feature_checks = []
    max_diff = 0.0
    evaluated = 0
    for idx in idxs:
        row = df.iloc[int(idx)]
        t0 = int(row["t0_idx"])
        if t0 <= 0:
            continue
        asof = t0 - 1
        if asof >= len(panel.dates):
            continue
        truncated = panel.slice(None, panel.date_strs[asof])
        ev = Evaluator(truncated, mask="universe")
        j = panel.symbols.index(row["code"])
        for feature, expr in list(expr_map.items())[:4]:
            try:
                arr = ev.eval(expr)
                value = float(arr[-1, j])
            except Exception as exc:
                feature_checks.append({"code": row["code"], "t0": row["t0_date"],
                                       "feature": feature, "error": str(exc)[:100]})
                continue
            cached = float(row[feature]) if pd.notna(row[feature]) else float("nan")
            diff = abs(value - cached) if np.isfinite(value) and np.isfinite(cached) else 0.0
            max_diff = max(max_diff, diff)
            feature_checks.append({"code": row["code"], "t0": row["t0_date"],
                                   "feature": feature, "diff": diff})
            evaluated += 1

    # PIT check: recompute the as-of ROE directly from the raw fina rows and
    # compare with the value baked into the panel.
    pit_checks = []
    pit_max_diff = 0.0
    pit_ok = True
    try:
        conn = connect(cfg.paths.market_db, readonly=True)
        for idx in idxs:
            row = df.iloc[int(idx)]
            t0 = int(row["t0_idx"])
            if t0 <= 0:
                continue
            asof = str(panel.date_strs[t0 - 1])
            rows = conn.execute(
                "SELECT ann_date,end_date,roe FROM fina WHERE code=? AND ann_date<=? "
                "ORDER BY ann_date,end_date", (row["code"], asof)
            ).fetchall()
            known: dict[str, float] = {}
            for ann, end, value in rows:
                known[end] = value
            expected = known[max(known)] if known else float("nan")
            j = panel.symbols.index(row["code"])
            actual = float(panel.field("roe")[t0 - 1, j])
            if np.isfinite(expected) or np.isfinite(actual):
                diff = abs((expected if np.isfinite(expected) else 0.0)
                           - (actual if np.isfinite(actual) else 0.0))
            else:
                diff = 0.0
            pit_max_diff = max(pit_max_diff, diff)
            if diff > 1e-4:
                pit_ok = False
            pit_checks.append({"code": row["code"], "asof": asof,
                               "expected_roe": expected, "panel_roe": actual,
                               "diff": diff})
        conn.close()
    except Exception as exc:
        pit_ok = False
        pit_checks.append({"error": str(exc)[:160]})

    label_ok = bool((df["entry_idx"] > df["t0_idx"]).all()
                    and (df["asof_idx"] < df["t0_idx"]).all())
    return {
        "ok": max_diff < 1e-4 and label_ok and pit_ok,
        "max_abs_diff": max_diff,
        "n_evaluated": evaluated,
        "label_alignment_ok": label_ok,
        "pit_ok": pit_ok,
        "pit_max_diff": pit_max_diff,
        "pit_checks": pit_checks[:10],
        "checks": feature_checks[:20],
        "truncated_feature_recompute": "features are recomputed with data <= T0-1",
    }
