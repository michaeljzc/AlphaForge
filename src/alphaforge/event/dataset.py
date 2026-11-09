"""Event-cross-section dataset assembly.

One row = one launch event.  Features are evaluated at ``T0-1`` (the last
tradable close before the launch) and labels start at ``T0``; the time gate is
therefore enforced by construction and independently audited in
:mod:`alphaforge.event.audit`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.event.detector import EventConfig, detect_events
from alphaforge.event.labels import label_events, tier_summary
from alphaforge.expr import Evaluator
from alphaforge.expr.library import FactorDef, default_factor_names, get_factor
from alphaforge.utils import write_json


@dataclass
class EventDataset:
    events: pd.DataFrame
    features: list[str]
    factor_map: dict[str, str]
    config: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.events)

    def summary(self) -> dict[str, Any]:
        s = tier_summary(self.events)
        s.update({
            "start": str(self.events["t0_date"].min()) if len(self.events) else None,
            "end": str(self.events["t0_date"].max()) if len(self.events) else None,
            "n_features": len(self.features),
            "codes": int(self.events["code"].nunique()) if len(self.events) else 0,
        })
        return s


def build_event_dataset(panel: Panel, cfg: Config | None = None,
                        factor_names: Sequence[str] | None = None,
                        factor_defs: Sequence[FactorDef] | None = None,
                        save: bool = False) -> EventDataset:
    cfg = cfg or load_config()
    ec = EventConfig.from_config(cfg)
    events = detect_events(panel, cfg, event_cfg=ec)
    if events.empty:
        return EventDataset(events=events, features=[], factor_map={},
                            config=ec.__dict__)
    events = label_events(panel, events, cfg, event_cfg=ec)

    if factor_defs is None:
        names = list(factor_names or default_factor_names())
        factor_defs = [get_factor(n) for n in names]
    factor_map = {f.name: f.expression for f in factor_defs}
    ev = Evaluator(panel, mask="universe")
    sym = {c: i for i, c in enumerate(panel.symbols)}
    t0 = events["t0_idx"].to_numpy(dtype=int)
    cols = np.array([sym[c] for c in events["code"]], dtype=int)
    asof = np.maximum(t0 - 1, 0)

    feature_rows: dict[str, np.ndarray] = {}
    for f in factor_defs:
        arr = ev.eval(f.expression)
        feature_rows[f.name] = np.asarray(arr[asof, cols], dtype=np.float64)
    features = pd.DataFrame(feature_rows, index=events.index)
    # avoid collisions with event-level columns (e.g. log_mv is both a factor
    # name and an event descriptor)
    collisions = [c for c in features.columns if c in events.columns]
    if collisions:
        features = features.rename(columns={c: f"f_{c}" for c in collisions})
    # event-level (non-expression) features
    for col in ("vol_ratio", "pct_chg", "turnover_pct", "amount", "close", "log_mv"):
        if col in events.columns:
            features[f"ev_{col}"] = events[col].to_numpy()

    events = pd.concat([events, features], axis=1)
    feature_cols = list(features.columns)
    events["section"] = (events["t0_idx"] // max(1, ec.cross_section_days)).astype(int)
    events["asof_idx"] = asof

    ds = EventDataset(events=events, features=feature_cols, factor_map=factor_map,
                      config=ec.__dict__)
    if save:
        path = cfg.paths.data / "events" / "events.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(path, index=False)
        write_json(cfg.paths.data / "events" / "events_summary.json", ds.summary())
    return ds
