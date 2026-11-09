"""Factor evaluation: IC / ICIR / quantile / turnover / gate.

All statistics are cross-sectional and date-by-date; the same code path is
reused for the calendar cross-section and (via the event layer) for event
cross-sections.
"""

from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.expr import Evaluator
from alphaforge.expr.library import FACTORS, FactorDef, get_factor
from alphaforge.preprocess import coverage, preprocess


# --------------------------------------------------------------------------
# ranking / correlation primitives
# --------------------------------------------------------------------------
def rank_pct(x: np.ndarray, valid: np.ndarray) -> np.ndarray:
    T, N = x.shape
    order = np.argsort(np.where(valid, x, np.inf), axis=1, kind="stable")
    ranks = np.empty((T, N), dtype=np.float64)
    np.put_along_axis(ranks, order,
                      np.broadcast_to(np.arange(N, dtype=np.float64), (T, N)), axis=1)
    cnt = valid.sum(axis=1, keepdims=True)
    return np.where(valid, (ranks + 0.5) / np.maximum(cnt, 1), np.nan)


def row_corr(a: np.ndarray, b: np.ndarray, valid: np.ndarray,
             min_names: int = 30) -> np.ndarray:
    n = valid.sum(axis=1).astype(np.float64)
    x = np.where(valid, a, 0.0)
    y = np.where(valid, b, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mx = x.sum(1) / n
        my = y.sum(1) / n
        # deviations must be zero outside the valid set, otherwise invalid
        # cells (encoded as 0) leak a -mean term into the covariance
        dx = np.where(valid, a - mx[:, None], 0.0)
        dy = np.where(valid, b - my[:, None], 0.0)
        cov = (dx * dy).sum(1)
        vx = (dx * dx).sum(1)
        vy = (dy * dy).sum(1)
        corr = cov / np.sqrt(vx * vy)
    ok = (n >= min_names) & (vx > 1e-18) & (vy > 1e-18)
    return np.where(ok, corr, np.nan)


def cross_section_ic(factor: np.ndarray, fwd: np.ndarray, mask: np.ndarray,
                     dates: Sequence[Any] | None = None, min_names: int = 30,
                     method: str = "spearman") -> pd.Series:
    valid = mask & np.isfinite(factor) & np.isfinite(fwd)
    f = np.asarray(factor, dtype=np.float64)
    r = np.asarray(fwd, dtype=np.float64)
    if method == "spearman":
        f = rank_pct(f, valid)
        r = rank_pct(r, valid)
    ic = row_corr(f, r, valid, min_names=min_names)
    index = pd.DatetimeIndex(dates) if dates is not None else pd.RangeIndex(len(ic))
    return pd.Series(ic, index=index, name="ic").dropna()


def _basic_stats(arr: np.ndarray, horizon: int) -> dict[str, Any]:
    n = int(len(arr))
    if n == 0:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "icir": float("nan"),
                "t_stat": float("nan"), "positive_rate": float("nan"), "hit_rate": float("nan")}
    mean = float(np.nanmean(arr))
    std = float(np.nanstd(arr, ddof=1)) if n > 1 else float("nan")
    icir = mean / std if std and math.isfinite(std) and std > 0 else float("nan")
    t = icir * math.sqrt(n) if math.isfinite(icir) else float("nan")
    pos = float(np.mean(arr > 0))
    return {
        "n": n, "mean": mean, "std": std, "icir": icir, "t_stat": t,
        "positive_rate": pos, "hit_rate": max(pos, 1 - pos), "horizon": horizon,
    }


def ic_stats(ic: pd.Series, horizon: int = 5, periods_per_year: int = 252) -> dict[str, Any]:
    """Daily and monthly IC statistics.

    The gate thresholds in the research report (|IC|>0.03, ICIR>0.5) are
    monthly-frequency conventions.  Daily ICs of overlapping h-day returns are
    autocorrelated, so the platform reports **both** and gates on the monthly
    aggregation (or on the daily series when the history is too short).
    """
    arr = ic.to_numpy(dtype=np.float64)
    daily = _basic_stats(arr, horizon)
    n = daily["n"]
    n_eff = max(1.0, n / max(1, horizon))
    daily["t_stat_overlap_adj"] = (
        daily["icir"] * math.sqrt(n_eff) if math.isfinite(daily["icir"]) else float("nan")
    )
    daily["n_eff"] = n_eff

    monthly: dict[str, Any] = {}
    if isinstance(ic.index, pd.DatetimeIndex) and n > 20:
        m = ic.resample("ME").mean().dropna()
        monthly = _basic_stats(m.to_numpy(dtype=np.float64), max(1, horizon))
        monthly["t_stat"] = (monthly["icir"] * math.sqrt(monthly["n"])
                             if math.isfinite(monthly["icir"]) else float("nan"))
    key = monthly or daily
    out = dict(daily)
    out.update({
        "monthly": monthly,
        "mean_monthly": key["mean"],
        "std_monthly": key["std"],
        "icir_monthly": key["icir"],
        "hit_rate_monthly": key["hit_rate"],
        "positive_rate_monthly": key["positive_rate"],
        "n_months": key["n"],
        "t_stat_monthly": key.get("t_stat", float("nan")),
        "gate_frequency": "monthly" if monthly else "daily",
    })
    return out


def _spearman_1d(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


# --------------------------------------------------------------------------
# quantile / long-short
# --------------------------------------------------------------------------
def quantile_returns(factor: np.ndarray, fwd: np.ndarray, mask: np.ndarray,
                     q: int = 5, min_names: int = 30,
                     dates: Sequence[Any] | None = None) -> pd.DataFrame:
    valid = mask & np.isfinite(factor) & np.isfinite(fwd)
    ranks = rank_pct(np.asarray(factor, dtype=np.float64), valid)
    with np.errstate(invalid="ignore"):
        bucket = np.minimum((ranks * q).astype(np.int64), q - 1)
    bucket = np.where(valid, bucket, -1)
    out = {}
    for k in range(q):
        w = valid & (bucket == k)
        cnt = w.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            vals = np.where(w, fwd, 0.0).sum(axis=1) / np.maximum(cnt, 1)
        vals = np.where(cnt >= min(min_names, 5), vals, np.nan)
        out[f"Q{k + 1}"] = vals
    index = pd.DatetimeIndex(dates) if dates is not None else pd.RangeIndex(len(ranks))
    return pd.DataFrame(out, index=index)


def quantile_summary(qret: pd.DataFrame, horizon: int = 5,
                     cost_bps: float = 0.0,
                     turnover: float | None = None
                     ) -> tuple[dict[str, Any], pd.DataFrame, pd.Series]:
    if qret.empty:
        return {}, pd.DataFrame(), pd.Series(dtype=float)
    means = qret.mean()
    stds = qret.std()
    n = len(qret)
    ann_factor = 252 / max(horizon, 1)
    ls = (qret.iloc[:, -1] - qret.iloc[:, 0]).dropna()
    ls_mean = float(ls.mean()) if len(ls) else float("nan")
    ls_std = float(ls.std()) if len(ls) > 1 else float("nan")
    sharpe = ls_mean / ls_std * math.sqrt(ann_factor) if ls_std and math.isfinite(ls_std) else float("nan")
    cost = 0.0
    if cost_bps and turnover is not None:
        cost = 2.0 * turnover * cost_bps / 1e4
    net_ls_mean = ls_mean - cost
    # non-overlapping periods for compounding: a 5-day forward return observed
    # every day must not be compounded daily (that would exaggerate the curve)
    step = max(1, horizon)
    q_ns = qret.iloc[::step]
    ls_ns = (q_ns.iloc[:, -1] - q_ns.iloc[:, 0]).dropna()
    ls_cum = (1 + ls_ns).cumprod()
    dd = float((ls_cum / ls_cum.cummax() - 1).min()) if len(ls_cum) else float("nan")
    q_cum = (1 + q_ns.fillna(0)).cumprod()
    return {
        "mean": {c: float(means[c]) for c in qret.columns},
        "std": {c: float(stds[c]) for c in qret.columns},
        "annualized": {c: float(means[c] * ann_factor) for c in qret.columns},
        "long_short": {
            "mean": ls_mean,
            "std": ls_std,
            "sharpe": sharpe,
            "annualized": ls_mean * ann_factor,
            "net_mean": net_ls_mean,
            "net_annualized": net_ls_mean * ann_factor,
            "cost_drag": cost,
            "max_drawdown": dd,
            "win_rate": float((ls_ns > 0).mean()) if len(ls_ns) else float("nan"),
            "n": int(len(ls_ns)),
        },
        "monotonicity": _spearman_1d(np.arange(len(means)), means.to_numpy()),
        "n_periods": n,
    }, q_cum, ls_cum


# --------------------------------------------------------------------------
# turnover
# --------------------------------------------------------------------------
def top_turnover(factor: np.ndarray, mask: np.ndarray, q: int = 5, step: int = 5,
                 min_names: int = 30) -> dict[str, Any]:
    valid = mask & np.isfinite(factor)
    ranks = rank_pct(np.asarray(factor, dtype=np.float64), valid)
    top = valid & (ranks >= 1.0 - 1.0 / q)
    T = factor.shape[0]
    turnovers = []
    prev: set[int] | None = None
    idxs = list(range(0, T, max(1, step)))
    for t in idxs:
        cols = np.flatnonzero(top[t])
        if len(cols) < min_names:
            continue
        cur = set(int(c) for c in cols)
        if prev is not None and prev:
            inter = len(cur & prev)
            turnovers.append(1.0 - inter / max(len(prev), 1))
        prev = cur
    return {
        "mean": float(np.mean(turnovers)) if turnovers else float("nan"),
        "series": pd.Series(turnovers),
        "n": len(turnovers),
    }


def factor_autocorr(factor: np.ndarray, mask: np.ndarray, lag: int = 1,
                    min_names: int = 30) -> float:
    valid = mask & np.isfinite(factor)
    ranks = rank_pct(np.asarray(factor, dtype=np.float64), valid)
    if lag >= len(ranks):
        return float("nan")
    a = ranks[lag:]
    b = ranks[:-lag]
    v = valid[lag:] & valid[:-lag]
    corr = row_corr(a, b, v, min_names=min_names)
    return float(np.nanmean(corr)) if np.isfinite(corr).any() else float("nan")


# --------------------------------------------------------------------------
# gate
# --------------------------------------------------------------------------
def gate(primary: dict[str, Any], qsum: dict[str, Any], coverage_value: float,
         cfg: Config) -> dict[str, Any]:
    min_ic = float(cfg.get("evaluation.min_ic", 0.03))
    min_icir = float(cfg.get("evaluation.min_icir", 0.5))
    min_hit = float(cfg.get("evaluation.min_positive_rate", 0.55))
    min_names = int(cfg.get("evaluation.min_names_per_date", 30))
    checks = {}

    ic_abs = abs(primary.get("mean_monthly", primary.get("mean", float("nan"))))
    icir_abs = abs(primary.get("icir_monthly", primary.get("icir", float("nan"))))
    hit = primary.get("hit_rate_monthly", primary.get("hit_rate", float("nan")))
    n_months = int(primary.get("n_months", 0) or 0)
    mono = abs(qsum.get("monotonicity", float("nan")))
    checks["ic"] = {
        "value": ic_abs, "threshold": min_ic, "pass": bool(ic_abs >= min_ic),
        "label": "|IC|",
    }
    checks["icir"] = {
        "value": icir_abs, "threshold": min_icir, "pass": bool(icir_abs >= min_icir),
        "label": "|ICIR|",
    }
    checks["hit_rate"] = {
        "value": hit, "threshold": min_hit,
        "pass": bool(hit >= min_hit), "label": "月度方向命中率",
    }
    checks["monotonicity"] = {
        "value": mono, "threshold": 0.5, "pass": bool(mono >= 0.5),
        "label": "分层单调性",
    }
    checks["coverage"] = {
        "value": coverage_value, "threshold": 0.5, "pass": bool(coverage_value >= 0.5),
        "label": "覆盖率",
    }
    net_dir = qsum.get("long_short", {}).get("directional_net_annualized", float("nan"))
    checks["cost_edge"] = {
        "value": net_dir, "threshold": 0.0, "pass": bool(net_dir > 0),
        "label": "方向调整扣费后年化",
    }
    checks["sample"] = {
        "value": max(n_months, 0), "threshold": 24,
        "pass": bool(n_months >= 24 or primary.get("n", 0) >= 100), "label": "样本期数",
    }
    passed = [k for k, v in checks.items() if v["pass"]]
    if all(checks[k]["pass"] for k in ("ic", "icir", "sample")):
        verdict = "PASS" if all(v["pass"] for v in checks.values()) else "WATCH"
    elif checks["ic"]["pass"]:
        verdict = "WATCH"
    else:
        verdict = "REJECT"
    return {
        "verdict": verdict,
        "checks": checks,
        "n_passed": len(passed),
        "reasons": [f"{checks[k]['label']} {checks[k]['value']:.3g} "
                    f"{'≥' if checks[k]['pass'] else '<'} {checks[k]['threshold']:.3g}"
                    for k in checks],
    }


# --------------------------------------------------------------------------
# report object
# --------------------------------------------------------------------------
@dataclass
class FactorReport:
    name: str
    expression: str
    category: str = ""
    description: str = ""
    direction: int = 1
    period: dict[str, Any] = field(default_factory=dict)
    coverage: float = float("nan")
    ic: dict[int, dict[str, Any]] = field(default_factory=dict)
    primary_horizon: int = 5
    quantile: dict[str, Any] = field(default_factory=dict)
    turnover: dict[str, Any] = field(default_factory=dict)
    autocorr: float = float("nan")
    gate: dict[str, Any] = field(default_factory=dict)
    neutralized: bool = True
    extra: dict[str, Any] = field(default_factory=dict)
    qret: pd.DataFrame | None = None
    q_curves: pd.DataFrame | None = None
    ls_curve: pd.Series | None = None
    ic_series: dict[int, pd.Series] = field(default_factory=dict)

    def to_dict(self, include_checks: bool = True) -> dict[str, Any]:
        d = {
            "name": self.name,
            "expression": self.expression,
            "category": self.category,
            "description": self.description,
            "direction": self.direction,
            "period": self.period,
            "coverage": self.coverage,
            "primary_horizon": self.primary_horizon,
            "ic": {str(k): v for k, v in self.ic.items()},
            "quantile": {k: v for k, v in self.quantile.items() if k != "curves"},
            "turnover": {k: v for k, v in self.turnover.items() if k != "series"},
            "autocorr": self.autocorr,
            "neutralized": self.neutralized,
            "extra": self.extra,
        }
        if include_checks:
            d["gate"] = self.gate
        return d

    @property
    def verdict(self) -> str:
        return self.gate.get("verdict", "NA")


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def evaluate_factor(panel: Panel, expr: str, name: str = "", cfg: Config | None = None,
                    horizons: Iterable[int] | None = None, start: str | None = None,
                    end: str | None = None, mask: str | np.ndarray = "universe",
                    do_preprocess: bool = True, q: int | None = None,
                    cost_bps: float | None = None,
                    evaluator: Evaluator | None = None,
                    description: str = "") -> FactorReport:
    cfg = cfg or load_config()
    horizons = list(horizons or cfg.get("evaluation.horizons", [1, 5, 10, 20, 60]))
    primary_h = int(cfg.get("evaluation.primary_horizon", 5))
    if primary_h not in horizons:
        horizons = sorted(set(horizons + [primary_h]))
    q = int(q or cfg.get("evaluation.quantiles", 5))
    cost_bps = float(cost_bps if cost_bps is not None else cfg.get("evaluation.cost_bps", 30))
    min_names = int(cfg.get("evaluation.min_names_per_date", 30))

    base_mask = panel.mask(mask) if isinstance(mask, str) else np.asarray(mask, dtype=bool)
    date_ok = panel.date_mask(start, end)[:, None]
    eval_mask = base_mask & date_ok

    ev = evaluator or Evaluator(panel, mask=base_mask)
    if expr in FACTORS:
        fdef = FACTORS[expr]
        if not name:
            name = expr
        if not description:
            description = fdef.description
        expr = fdef.expression
    elif expr.startswith("a158_"):
        fdef = get_factor(expr)
        if not name:
            name = expr
        if not description:
            description = fdef.description
        expr = fdef.expression
    raw = ev.eval(expr)
    processed = preprocess(raw, panel, cfg, mask=eval_mask) if do_preprocess else np.where(eval_mask, raw, np.nan)
    cov = coverage(processed, eval_mask)

    ic_by_h: dict[int, dict[str, Any]] = {}
    ic_series: dict[int, pd.Series] = {}
    for h in horizons:
        fwd = panel.forward_return(h)
        ic = cross_section_ic(processed, fwd, eval_mask, panel.dates, min_names)
        ic_by_h[h] = ic_stats(ic, horizon=h)
        ic_series[h] = ic

    fwd_primary = panel.forward_return(primary_h)
    qret = quantile_returns(processed, fwd_primary, eval_mask, q=q,
                            min_names=min_names, dates=panel.dates)
    qsum, q_curves, ls_curve = quantile_summary(qret, horizon=primary_h, cost_bps=cost_bps)
    if not qsum:
        qsum = {}
    turn = top_turnover(processed, eval_mask, q=q, step=max(1, primary_h),
                        min_names=min_names)
    qsum["cost_bps"] = cost_bps
    qsum["turnover"] = turn["mean"]
    # attach cost-adjusted stats
    if qsum:
        cost = 2.0 * turn["mean"] * cost_bps / 1e4 if math.isfinite(turn["mean"]) else 0.0
        qsum["long_short"]["cost_drag"] = cost
        qsum["long_short"]["net_mean"] = qsum["long_short"]["mean"] - cost
        qsum["long_short"]["net_annualized"] = qsum["long_short"]["net_mean"] * 252 / max(primary_h, 1)
    auto = factor_autocorr(processed, eval_mask, lag=max(1, primary_h), min_names=min_names)

    ic_sign = 1 if ic_by_h[primary_h].get("mean", 0) >= 0 else -1
    if qsum:
        qsum["direction"] = ic_sign
        net = qsum["long_short"].get("net_annualized", float("nan"))
        qsum["long_short"]["directional_net_annualized"] = ic_sign * net
        qsum["long_short"]["directional_annualized"] = ic_sign * qsum["long_short"].get("annualized", float("nan"))

    report = FactorReport(
        name=name or expr,
        expression=expr,
        description=description,
        period={"start": str(panel.dates[0]) if start is None else start,
                "end": str(panel.dates[-1]) if end is None else end,
                "n_dates": int(eval_mask[:, 0].sum())},
        coverage=cov,
        ic=ic_by_h,
        primary_horizon=primary_h,
        quantile=qsum,
        turnover=turn,
        autocorr=auto,
        neutralized=bool(do_preprocess),
        qret=qret,
        q_curves=q_curves,
        ls_curve=ls_curve,
        ic_series=ic_series,
    )
    report.gate = gate(ic_by_h[primary_h], qsum, cov, cfg)
    return report


def evaluate_many(panel: Panel, factors: Sequence[FactorDef], cfg: Config | None = None,
                  **kwargs) -> tuple[list[FactorReport], pd.DataFrame]:
    cfg = cfg or load_config()
    reports: list[FactorReport] = []
    evaluator = Evaluator(panel, mask="universe")
    for f in factors:
        rep = evaluate_factor(panel, f.expression, name=f.name, cfg=cfg,
                              description=f.description, evaluator=evaluator, **kwargs)
        rep.category = f.category
        rep.direction = f.direction
        reports.append(rep)
    rows = []
    for r in reports:
        p = r.ic.get(r.primary_horizon, {})
        rows.append({
            "name": r.name, "category": r.category,
            "ic": p.get("mean_monthly", p.get("mean")),
            "icir": p.get("icir_monthly", p.get("icir")),
            "hit": p.get("hit_rate_monthly", p.get("hit_rate")),
            "n": p.get("n"), "n_months": p.get("n_months"),
            "mono": r.quantile.get("monotonicity"),
            "ls_ann": r.quantile.get("long_short", {}).get("annualized"),
            "net_ann": r.quantile.get("long_short", {}).get("net_annualized"),
            "turnover": r.turnover.get("mean"),
            "verdict": r.verdict, "coverage": r.coverage,
        })
    return reports, pd.DataFrame(rows).sort_values("ic", key=lambda s: s.abs(), ascending=False)


def evaluate_library(panel: Panel, cfg: Config | None = None,
                     category: str | None = None, names: Iterable[str] | None = None,
                     start: str = "2021-01-01", end: str | None = None,
                     horizons: Iterable[int] | None = None,
                     save: bool = True, merge: bool = True,
                     verbose: bool = True) -> list[FactorReport]:
    """Evaluate a whole factor-library slice (e.g. all 101 WQ alphas)."""
    from alphaforge.expr.library import list_factors

    cfg = cfg or load_config()
    if names:
        wanted = set(names)
        factors = [f for f in list_factors() if f.name in wanted]
    elif category and category != "all":
        factors = list_factors(category)
    else:
        factors = list_factors()
    if not factors:
        return []
    ev = Evaluator(panel, mask="universe")
    reports: list[FactorReport] = []
    t0 = time.time()
    for i, f in enumerate(factors, 1):
        rep = evaluate_factor(panel, f.expression, name=f.name, cfg=cfg,
                              description=f.description, start=start, end=end,
                              horizons=horizons, evaluator=ev)
        rep.category = f.category
        rep.direction = f.direction
        reports.append(rep)
        if verbose and (i % 10 == 0 or i == len(factors)):
            p = rep.ic.get(rep.primary_horizon, {})
            print(f"[batch] {i}/{len(factors)} {f.name} "
                  f"IC={p.get('mean_monthly', float('nan')):.4f} "
                  f"{time.time()-t0:.0f}s", flush=True)
    if save:
        from alphaforge.report.artifacts import save_factor_artifacts

        info = save_factor_artifacts(reports, cfg.paths.reports / "artifacts" / "factors",
                                     merge=merge)
        if verbose:
            print(f"[batch] saved {info['n']} snapshots -> {info['dir']}")
    return reports


def factor_correlation(panel: Panel, arrays: dict[str, np.ndarray], mask: np.ndarray,
                       max_dates: int = 120, min_names: int = 30) -> pd.DataFrame:
    """Average cross-sectional rank correlation, sampled over dates for speed."""
    names = list(arrays)
    T = panel.shape[0]
    idxs = np.linspace(0, T - 1, min(max_dates, T)).astype(int)
    out = pd.DataFrame(np.eye(len(names)), index=names, columns=names)
    ranks = {}
    for name, arr in arrays.items():
        valid = mask & np.isfinite(arr)
        ranks[name] = rank_pct(np.asarray(arr, dtype=np.float64), valid)
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            b = names[j]
            corrs = []
            for t in idxs:
                v = np.isfinite(ranks[a][t]) & np.isfinite(ranks[b][t])
                if v.sum() < min_names:
                    continue
                c = _spearman_1d(ranks[a][t][v], ranks[b][t][v])
                if math.isfinite(c):
                    corrs.append(c)
            val = float(np.mean(corrs)) if corrs else float("nan")
            out.iloc[i, j] = out.iloc[j, i] = val
    return out
