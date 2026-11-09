"""Multi-factor combination and target-portfolio construction."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.evaluate.core import cross_section_ic, ic_stats
from alphaforge.expr import Evaluator
from alphaforge.expr.library import FactorDef
from alphaforge.preprocess import preprocess


@dataclass
class CompositeResult:
    scores: np.ndarray
    contributions: dict[str, np.ndarray]
    signs: dict[str, int]
    weights: dict[str, float]
    ic: dict[str, float]
    method: str
    meta: dict[str, Any] = field(default_factory=dict)


def combine_factors(panel: Panel, factors: Sequence[FactorDef], cfg: Config | None = None,
                    method: str = "equal", train_start: str | None = None,
                    train_end: str | None = None, mask: str = "universe",
                    horizon: int | None = None) -> CompositeResult:
    """Build a composite score from factors.

    ``method``:
      * ``equal``       -- direction prior, equal weights
      * ``ic_weighted`` -- sign and weight learned on ``[train_start, train_end]``
    Learning on the training window only keeps the composite out-of-sample
    usable for the validation/test window.
    """
    cfg = cfg or load_config()
    horizon = int(horizon or cfg.get("evaluation.primary_horizon", 5))
    base_mask = panel.mask(mask)
    ev = Evaluator(panel, mask=base_mask)
    train_mask = base_mask & panel.date_mask(train_start, train_end)[:, None]
    fwd = panel.forward_return(horizon)

    contrib: dict[str, np.ndarray] = {}
    signs: dict[str, int] = {}
    raw_ic: dict[str, float] = {}
    weights: dict[str, float] = {}

    for f in factors:
        arr = ev.eval(f.expression)
        processed = preprocess(arr, panel, cfg, mask=base_mask)
        if method == "ic_weighted":
            ic = cross_section_ic(processed, fwd, train_mask, panel.dates,
                                  min_names=int(cfg.get("evaluation.min_names_per_date", 30)))
            ic_mean = float(ic.mean()) if len(ic) else 0.0
            sign = 1 if ic_mean >= 0 else -1
            weight = abs(ic_mean)
            raw_ic[f.name] = ic_mean
        else:
            sign = 1 if f.direction >= 0 else -1
            weight = 1.0
            raw_ic[f.name] = float(f.direction)
        signs[f.name] = sign
        weights[f.name] = weight
        contrib[f.name] = sign * weight * processed

    total = sum(weights.values())
    if total > 0:
        for k in weights:
            weights[k] /= total

    composite = np.zeros(panel.shape, dtype=np.float64)
    for name, arr in contrib.items():
        composite += weights[name] * arr
    composite = np.where(base_mask, composite, np.nan)
    composite = preprocess(composite, panel, cfg, mask=base_mask)
    return CompositeResult(scores=composite.astype(np.float32), contributions=contrib,
                           signs=signs, weights=weights, ic=raw_ic, method=method,
                           meta={"horizon": horizon, "train": [train_start, train_end]})


def _pick_names(score: np.ndarray, eligible: np.ndarray, industry_id: np.ndarray,
                prev: list[int], top_n: int, buffer: int,
                max_per_industry: int, min_score: float = -np.inf) -> list[int]:
    if eligible.sum() == 0:
        return []
    order = np.argsort(np.where(eligible, -score, np.inf))
    rank = {int(c): i for i, c in enumerate(order)}
    chosen: list[int] = []
    counts: dict[int, int] = {}

    def add(c: int) -> bool:
        ind = int(industry_id[c])
        if counts.get(ind, 0) >= max_per_industry:
            return False
        current = score[c]
        if current < min_score:
            return False
        chosen.append(c)
        counts[ind] = counts.get(ind, 0) + 1
        return True

    # buffer: keep incumbents that are still within top_n + buffer
    for c in prev:
        if c < len(score) and eligible[c] and rank.get(c, 10**9) < top_n + buffer:
            add(c)
        if len(chosen) >= top_n:
            break
    for c in order:
        c = int(c)
        if len(chosen) >= top_n:
            break
        if c in chosen:
            continue
        add(c)
    return chosen


def build_targets(panel: Panel, scores: np.ndarray, cfg: Config | None = None,
                  start: str | None = None, end: str | None = None,
                  rebalance_days: int = 5, top_n: int | None = None,
                  max_per_industry: int | None = None,
                  max_weight: float | None = None) -> dict[int, dict[str, float]]:
    """Return ``{signal_date_index: {code: weight}}``.

    Execution is at the next open; signal dates are every ``rebalance_days``
    trading days.  Weights are equal-weighted with per-name and per-industry
    caps; unallocated weight stays in cash.
    """
    cfg = cfg or load_config()
    top_n = int(top_n or cfg.get("portfolio.top_n", 50))
    buffer = int(cfg.get("portfolio.buffer", 10))
    max_weight = float(max_weight or cfg.get("backtest.max_weight", 0.05))
    max_per_industry = int(max_per_industry or max(3, math.ceil(top_n * 0.25)))
    base_mask = panel.mask("universe")
    date_mask = panel.date_mask(start, end)
    avail = np.flatnonzero(date_mask)
    if len(avail) == 0:
        return {}
    signal_idxs = list(range(avail[0], avail[-1] - 1, max(1, rebalance_days)))
    targets: dict[int, dict[str, float]] = {}
    prev: list[int] = []
    for t in signal_idxs:
        eligible = base_mask[t] & np.isfinite(scores[t])
        if eligible.sum() < 10:
            continue
        names = _pick_names(scores[t].astype(np.float64), eligible, panel.industry_id,
                            prev, top_n, buffer, max_per_industry)
        if len(names) < 5:
            continue
        w = min(1.0 / len(names), max_weight)
        targets[t] = {panel.symbols[c]: w for c in names}
        prev = names
    return targets


def target_frame(panel: Panel, targets: dict[int, dict[str, float]]) -> pd.DataFrame:
    rows = []
    for t, w in targets.items():
        for code, weight in w.items():
            rows.append({"date": panel.dates[t], "code": code, "weight": weight})
    if not rows:
        return pd.DataFrame(columns=["date", "code", "weight"])
    return pd.DataFrame(rows)
