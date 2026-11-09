"""End-to-end demo pipeline.

Steps: panel -> Qlib export/parity -> factor evaluation -> composite ->
A-share backtest -> T0 event dataset/IC/backtest -> optional GP mining ->
HTML report.  Every artefact is written under ``reports/`` and
``artifacts/factors/`` so a run can be inspected after the fact.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alphaforge.backtest.engine import BacktestResult, run_backtest
from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel, load_panel
from alphaforge.data.qlib_export import QlibExporter, verify_parity
from alphaforge.evaluate.core import evaluate_many, evaluate_factor, factor_correlation
from alphaforge.event.audit import audit_event_dataset
from alphaforge.event.dataset import build_event_dataset
from alphaforge.event.evaluate import event_backtest, event_ic, event_precision
from alphaforge.expr import Evaluator
from alphaforge.expr.library import (FACTORS, alpha158_factors, default_factor_names,
                                     get_factor)
from alphaforge.mining.gp import run_gp
from alphaforge.portfolio.combine import build_targets, combine_factors
from alphaforge.preprocess import preprocess
from alphaforge.report.artifacts import save_factor_artifacts
from alphaforge.report.html import build_demo_report
from alphaforge.utils import read_json, write_json


def _panel_info(panel: Panel) -> dict[str, Any]:
    return {
        "n_dates": int(panel.shape[0]),
        "n_symbols": int(panel.shape[1]),
        "start": panel.date_strs[0],
        "end": panel.date_strs[-1],
        "fields": len(panel.fields()),
        "masks": list(panel.masks),
        "universe_avg": float(panel.mask("universe").sum(axis=1).mean()),
    }


def _pick_best(reports):
    for verdict in ("PASS", "WATCH"):
        subset = [r for r in reports if r.verdict == verdict]
        if subset:
            return max(subset, key=lambda r: abs(r.ic.get(r.primary_horizon, {}).get(
                "mean_monthly", 0) or 0)).name
    if not reports:
        return ""
    return max(reports, key=lambda r: abs(r.ic.get(r.primary_horizon, {}).get(
        "mean_monthly", 0) or 0)).name


def run_demo(cfg: Config | None = None, quick: bool = True, mine: bool = True,
             report: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config()
    t_start = time.time()
    artifacts = cfg.paths.reports / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        print(f"[demo +{time.time()-t_start:6.1f}s] {msg}", flush=True)

    # 1. panel -----------------------------------------------------------
    log("加载面板")
    panel = load_panel(cfg)
    pinfo = _panel_info(panel)
    log(f"面板 {panel.shape} {pinfo['start']} ~ {pinfo['end']}")

    # 2. Qlib export + parity -------------------------------------------
    log("导出 Qlib 二进制并校验")
    export_meta = QlibExporter(cfg, panel).export(force=False)
    try:
        parity = verify_parity(cfg, n=2)
    except Exception as exc:
        parity = {"error": str(exc)[:200], "max_abs_diff": float("nan")}
    try:
        a158 = alpha158_factors()
    except Exception:
        a158 = []
    qlib_info = {
        **export_meta,
        "max_abs_diff": parity.get("max_abs_diff"),
        "alpha158": len(a158),
        "parity_checked": len(parity.get("checked", [])),
    }
    write_json(artifacts / "qlib.json", qlib_info)
    log(f"Qlib: {export_meta.get('symbols')} 只, parity max|diff|={qlib_info['max_abs_diff']}")
    native_path = artifacts / "qlib_native.json"
    qlib_native = read_json(native_path) if native_path.exists() else {}
    if qlib_native:
        icm = (qlib_native.get("ic") or {}).get("monthly_mean")
        log(f"载入 Qlib 原生结果: IC月={icm:.4f}" if icm is not None else "载入 Qlib 原生结果")

    # 3. factor evaluation ----------------------------------------------
    log("评估内置因子")
    names = default_factor_names()
    factors = [get_factor(n) for n in names]
    reports, _ = evaluate_many(panel, factors, cfg=cfg, start="2021-01-01",
                               end=cfg.data_end, horizons=[1, 5, 20, 60])
    rows = []
    for r in reports:
        p = r.ic.get(r.primary_horizon, {})
        q = r.quantile.get("long_short", {})
        rows.append({
            "name": r.name, "category": r.category,
            "ic": p.get("mean_monthly", p.get("mean")),
            "icir": p.get("icir_monthly", p.get("icir")),
            "hit": p.get("hit_rate_monthly", p.get("hit_rate")),
            "n": p.get("n"), "n_months": p.get("n_months"),
            "mono": r.quantile.get("monotonicity"),
            "ls_ann": q.get("annualized"), "net_ann": q.get("net_annualized"),
            "dir_net": q.get("directional_net_annualized"),
            "turnover": r.turnover.get("mean"),
            "verdict": r.verdict, "coverage": r.coverage,
        })
    leaderboard = pd.DataFrame(rows).sort_values("ic", key=lambda s: s.abs(), ascending=False)
    best_name = _pick_best(reports)
    factor_index = save_factor_artifacts(reports, artifacts / "factors", merge=True)
    log(f"完成 {len(reports)} 个因子，闸门 PASS/WATCH: "
        f"{sum(r.verdict != 'REJECT' for r in reports)}")

    # 4. correlation -----------------------------------------------------
    log("计算因子相关性")
    top_names = leaderboard["name"].head(12).tolist()
    ev = Evaluator(panel, mask="universe")
    arrays = {n: preprocess(ev.eval(get_factor(n).expression), panel, cfg,
                            mask=panel.mask("universe")) for n in top_names}
    corr = factor_correlation(panel, arrays, panel.mask("universe"), max_dates=80)

    # 5. composite + backtest -------------------------------------------
    log("构建组合并回测")
    comp = combine_factors(panel, factors, cfg=cfg, method="ic_weighted",
                           train_start="2021-01-01", train_end="2023-12-31")
    targets = build_targets(panel, comp.scores, cfg=cfg, start="2024-01-01",
                            end=cfg.data_end, rebalance_days=21, top_n=50)
    bt = run_backtest(panel, targets, cfg=cfg, start="2024-01-02", end=cfg.data_end)
    bt_payload = bt.to_dict()
    write_json(artifacts / "backtest.json", bt_payload)
    log(f"组合 CAGR={bt.metrics['cagr']:.2%} Sharpe={bt.metrics['sharpe']:.2f} "
        f"MDD={bt.metrics['max_drawdown']:.1%} turnover={bt.metrics['turnover_annual']:.1f}x")

    # 6. events ----------------------------------------------------------
    log("构建 T0 事件数据集")
    dataset = build_event_dataset(panel, cfg=cfg, save=True)
    ev_summary = dataset.summary()
    ev_ic = event_ic(dataset)
    best_ev = ev_ic.iloc[0] if not ev_ic.empty else None
    ev_bt = {}
    ev_prec = {}
    if best_ev is not None:
        ascending = best_ev["ic"] < 0
        ev_bt = event_backtest(dataset, panel, cfg=cfg, feature=best_ev["feature"],
                               top_frac=0.2, ascending=ascending, max_positions=30)
        ev_prec = event_precision(dataset, best_ev["feature"], ascending=ascending)
    audit = audit_event_dataset(panel, dataset, cfg=cfg, sample=8)
    write_json(artifacts / "events.json", {
        "summary": ev_summary,
        "ic": ev_ic.to_dict(orient="records") if not ev_ic.empty else [],
        "best_feature": best_ev["feature"] if best_ev is not None else None,
        "backtest": {k: v for k, v in ev_bt.items() if k not in ("trades",)},
        "precision": ev_prec, "audit": audit,
    })
    log(f"事件 {ev_summary.get('n_events')} 个; 强正 {ev_summary.get('tiers',{}).get('strong')}; "
        f"审计 {'通过' if audit.get('ok') else '未通过'}")

    # 7. GP --------------------------------------------------------------
    gp_result = None
    if mine:
        log("遗传规划挖掘（quick）")
        gp_result = run_gp(panel, cfg=cfg, save=True, register=False,
                           population=80 if quick else None,
                           generations=5 if quick else None,
                           top_eval=8 if quick else 12)
        write_json(artifacts / "gp.json", gp_result)
        log(f"GP 完成 evals={gp_result.get('evaluations')}")

    # 8. report ----------------------------------------------------------
    result = {
        "meta": {"generated": pd.Timestamp.now().isoformat(),
                 "elapsed_sec": round(time.time() - t_start, 1)},
        "panel": pinfo,
        "qlib": qlib_info,
        "qlib_native": qlib_native,
        "factor_reports": reports,
        "leaderboard": leaderboard,
        "factor_index": factor_index,
        "correlation": corr,
        "best_factor": best_name,
        "backtest": bt,
        "events": {"summary": ev_summary, "ic": ev_ic, "backtest": ev_bt,
                   "precision": ev_prec},
        "audit": audit,
        "gp": gp_result,
        "n_factors": len(FACTORS) + len(a158),
        "factor_library": len(FACTORS) + len(a158),
    }
    write_json(artifacts / "demo_summary.json", {
        "panel": pinfo, "qlib": qlib_info,
        "factor_library": len(FACTORS) + len(a158),
        "qlib_native": {"ic": qlib_native.get("ic", {}),
                        "qlib_backtest": {k: v for k, v in (qlib_native.get("qlib_backtest") or {}).items()
                                          if k not in ("equity", "dates", "benchmark_equity", "traceback")},
                        "alphaforge_backtest": qlib_native.get("alphaforge_backtest", {})},
        "leaderboard": leaderboard.to_dict(orient="records"),
        "backtest": bt.metrics,
        "events": ev_summary,
        "audit": audit,
        "best_factor": best_name,
        "elapsed_sec": result["meta"]["elapsed_sec"],
    })
    if report:
        log("生成 HTML 报告")
        path = build_demo_report(result, cfg)
        log(f"报告 -> {path}")
        result["report_path"] = str(path)
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="AlphaForge demo")
    ap.add_argument("--config", default=None)
    ap.add_argument("--full", action="store_true", help="完整 GP（200x15）")
    ap.add_argument("--no-mine", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()
    run_demo(load_config(args.config), quick=not args.full, mine=not args.no_mine,
             report=not args.no_report)
