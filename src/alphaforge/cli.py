"""AlphaForge command line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from alphaforge.config import load_config


def _fmt(x, digits=3):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    if not np.isfinite(v):
        return "-"
    return f"{v:.{digits}f}"


def _pct(x, digits=1):
    try:
        return f"{float(x)*100:.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("(empty)")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


# --------------------------------------------------------------------------
def cmd_ingest(args, cfg):
    from alphaforge.data.ingest import ingest

    ingest(cfg, indices=args.indices.split(",") if args.indices else None,
           start=args.start, end=args.end, limit=args.limit,
           codes=args.codes.split(",") if args.codes else None,
           skip=tuple(x for x in (args.skip or "").split(",") if x),
           interval=args.interval)


def cmd_build(args, cfg):
    from alphaforge.data.panel import load_panel
    from alphaforge.data.qlib_export import QlibExporter, verify_parity

    panel = load_panel(cfg, start=args.start, end=args.end, use_cache=not args.no_cache)
    print(f"panel: {panel.shape}  {panel.dates[0]} ~ {panel.dates[-1]}")
    print(f"fields: {len(panel.fields())}  masks: {', '.join(panel.masks)}")
    if args.export_qlib:
        meta = QlibExporter(cfg, panel).export(force=args.force)
        print(f"qlib export: {json.dumps(meta, ensure_ascii=False)}")
    if args.verify:
        print(json.dumps(verify_parity(cfg), ensure_ascii=False, indent=2)[:4000])


def cmd_factors(args, cfg):
    from alphaforge.expr.library import FACTORS, alpha158_factors, categories, get_factor, list_factors
    from alphaforge.expr.ops import list_ops

    if args.factor_cmd == "list":
        if args.category == "alpha158":
            items = alpha158_factors()
        elif args.category == "all":
            items = list_factors() + alpha158_factors()
        else:
            items = list_factors(args.category)
        _print_table([{"name": f.name, "category": f.category,
                       "description": f.description, "expression": f.expression[:70]}
                      for f in items],
                     ["name", "category", "description", "expression"])
        print(f"\nbuiltin={len(FACTORS)}  {categories()}")
        try:
            print(f"alpha158={len(alpha158_factors())}  all={len(FACTORS)+len(alpha158_factors())}")
        except Exception:
            pass
    elif args.factor_cmd == "ops":
        ops = list_ops(args.kind)
        _print_table([{"name": k, "arity": str(v.arity), "kind": v.kind, "doc": v.doc}
                      for k, v in sorted(ops.items())], ["name", "arity", "kind", "doc"])
    elif args.factor_cmd == "eval":
        from alphaforge.data.panel import load_panel
        from alphaforge.evaluate.core import evaluate_factor

        panel = load_panel(cfg)
        rep = evaluate_factor(panel, args.expression, name=args.expression[:40], cfg=cfg,
                              start=args.start, end=args.end,
                              horizons=[int(x) for x in args.horizons.split(",")])
        d = rep.to_dict()
        p = d["ic"][str(rep.primary_horizon)]
        print(f"factor      : {rep.name}")
        print(f"description : {rep.description or '-'}")
        print(f"expression  : {rep.expression}")
        print(f"period      : {d['period']['start']} ~ {d['period']['end']}  n={p.get('n')}")
        print(f"IC daily    : {_fmt(p.get('mean'), 4)}  ICIR={_fmt(p.get('icir'), 2)}")
        print(f"IC monthly  : {_fmt(p.get('mean_monthly'), 4)}  ICIR={_fmt(p.get('icir_monthly'), 2)}  "
              f"hit={_pct(p.get('hit_rate_monthly'))}")
        print(f"quantile    : {d['quantile'].get('mean')}")
        print(f"long-short  : ann={_pct(d['quantile']['long_short'].get('annualized'))}  "
              f"net={_pct(d['quantile']['long_short'].get('net_annualized'))}  "
              f"turnover={_fmt(d['turnover']['mean'], 2)}")
        print(f"gate        : {rep.verdict}  {d['gate'].get('reasons')}")
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2, default=float))
    elif args.factor_cmd == "batch":
        from alphaforge.data.panel import load_panel
        from alphaforge.evaluate.core import evaluate_library

        panel = load_panel(cfg)
        reps = evaluate_library(panel, cfg=cfg, category=args.category,
                                start=args.start, end=args.end,
                                horizons=[int(x) for x in args.horizons.split(",")],
                                save=not args.no_save)
        rows = []
        for r in reps:
            p = r.ic.get(r.primary_horizon, {})
            rows.append({"name": r.name, "category": r.category,
                         "ICm": _fmt(p.get("mean_monthly"), 4),
                         "ICIR": _fmt(p.get("icir_monthly"), 2),
                         "verdict": r.verdict})
        rows.sort(key=lambda x: abs(float(x["ICm"])) if x["ICm"] not in ("-", "nan") else 0, reverse=True)
        _print_table(rows[:30], ["name", "category", "ICm", "ICIR", "verdict"])
    elif args.factor_cmd == "mine":
        from alphaforge.data.panel import load_panel
        from alphaforge.mining.gp import run_gp

        panel = load_panel(cfg)
        res = run_gp(panel, cfg=cfg, register=args.register,
                     population=args.population, generations=args.generations,
                     top_eval=args.top)
        print(f"evaluations={res.get('evaluations')} elapsed={res.get('elapsed_sec')}s")
        for c in res.get("evaluated", [])[:10]:
            print(f"  IC train={_fmt(c.get('train_ic'), 4)} valid={_fmt(c.get('valid_ic'), 4)} "
                  f"test={_fmt(c.get('test_ic'), 4)}  {c.get('expression')}")


def cmd_backtest(args, cfg):
    from alphaforge.backtest.engine import run_backtest
    from alphaforge.data.panel import load_panel
    from alphaforge.expr.library import default_factor_names, get_factor
    from alphaforge.portfolio.combine import build_targets, combine_factors
    from alphaforge.utils import write_json

    panel = load_panel(cfg)
    factors = [get_factor(n) for n in default_factor_names()]
    comp = combine_factors(panel, factors, cfg=cfg, method=args.method,
                           train_start=args.train_start, train_end=args.train_end)
    targets = build_targets(panel, comp.scores, cfg=cfg, start=args.start, end=args.end,
                            rebalance_days=args.rebalance, top_n=args.top_n)
    bt = run_backtest(panel, targets, cfg=cfg, start=args.start, end=args.end)
    print(json.dumps(bt.metrics, ensure_ascii=False, indent=2, default=float))
    out = cfg.paths.reports / "artifacts" / "backtest_cli.json"
    write_json(out, bt.to_dict())
    print(f"saved -> {out}")


def cmd_event(args, cfg):
    from alphaforge.data.panel import load_panel
    from alphaforge.event.audit import audit_event_dataset
    from alphaforge.event.dataset import build_event_dataset
    from alphaforge.event.evaluate import event_backtest, event_ic, event_precision

    panel = load_panel(cfg)
    ds = build_event_dataset(panel, cfg=cfg, save=True)
    print(json.dumps(ds.summary(), ensure_ascii=False, indent=2, default=str))
    ic = event_ic(ds)
    print("\nevent IC (top 12):")
    print(ic.head(12).to_string(index=False))
    if not ic.empty:
        best = ic.iloc[0]
        bt = event_backtest(ds, panel, cfg=cfg, feature=best["feature"], top_frac=0.2,
                            ascending=best["ic"] < 0, max_positions=30)
        print("\nevent portfolio:")
        print(json.dumps({k: v for k, v in bt.items()
                          if k not in ("equity", "trades", "equity_dates")},
                         ensure_ascii=False, indent=2, default=float))
        print("\nprecision:", json.dumps(event_precision(ds, best["feature"],
                                                         ascending=best["ic"] < 0),
                                         ensure_ascii=False, default=float))
    if args.audit:
        print("\naudit:", json.dumps(audit_event_dataset(panel, ds, cfg=cfg, sample=6),
                                     ensure_ascii=False, indent=2, default=str)[:3000])


def cmd_qlib(args, cfg):
    from alphaforge.data.qlib_export import export_qlib, verify_parity

    if args.qlib_cmd == "verify":
        print(json.dumps(verify_parity(cfg), ensure_ascii=False, indent=2, default=float))
    elif args.qlib_cmd == "native":
        from alphaforge.qlib_native import run_qlib_native

        res = run_qlib_native(cfg, n_symbols=args.symbols, topk=args.topk,
                              n_drop=args.n_drop, run_backtest=not args.no_backtest)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=float))
    else:
        print(json.dumps(export_qlib(cfg, force=args.force), ensure_ascii=False, indent=2))


def cmd_demo(args, cfg):
    from alphaforge.pipeline.demo import run_demo

    run_demo(cfg, quick=not args.full, mine=not args.no_mine, report=not args.no_report)


def cmd_web(args, cfg):
    import uvicorn

    os.environ["ALPHAFORGE_CONFIG"] = str(cfg.path) if cfg.path else ""
    uvicorn.run("alphaforge.web.app:app", host=args.host, port=args.port, log_level="info")


def cmd_sources(args, cfg):
    from alphaforge.data.sources import (configured, fetch_datayes_daily,
                                         fetch_ifind_daily, probe_source, status,
                                         sync_datayes, sync_ifind)

    if args.sources_cmd == "status":
        print(json.dumps(status(probe=args.probe), ensure_ascii=False, indent=2))
    elif args.sources_cmd == "probe":
        print(json.dumps(probe_source(args.source), ensure_ascii=False, indent=2))
    elif args.sources_cmd == "fetch":
        codes = [c for c in (args.codes or "").split(",") if c]
        if not codes:
            raise SystemExit("需要 --codes 000001,600000")
        if args.source == "datayes":
            res = sync_datayes(cfg, codes, args.start, args.end, write=args.write)
        elif args.source == "ifind":
            res = sync_ifind(cfg, codes, args.start, args.end, adjust=args.adjust,
                             write=args.write)
        else:
            raise SystemExit("--source 仅支持 datayes / ifind")
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alphaforge",
                                     description="AlphaForge: Qlib-native factor research platform")
    parser.add_argument("--config", default=None, help="YAML 配置文件")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Tushare 数据摄取")
    p.add_argument("--indices", default=None)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--codes", default=None)
    p.add_argument("--skip", default="")
    p.add_argument("--interval", type=float, default=0.13)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("build", help="构建面板并导出 Qlib 格式")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--export-qlib", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("factors", help="因子库 / 评估 / 挖掘")
    fsub = p.add_subparsers(dest="factor_cmd", required=True)
    fl = fsub.add_parser("list")
    fl.add_argument("--category", default=None)
    fl.set_defaults(func=cmd_factors)
    fo = fsub.add_parser("ops")
    fo.add_argument("--kind", default=None)
    fo.set_defaults(func=cmd_factors)
    fe = fsub.add_parser("eval")
    fe.add_argument("expression")
    fe.add_argument("--start", default="2021-01-01")
    fe.add_argument("--end", default=None)
    fe.add_argument("--horizons", default="1,5,20,60")
    fe.add_argument("--json", action="store_true")
    fe.set_defaults(func=cmd_factors)
    fb = fsub.add_parser("batch")
    fb.add_argument("--category", default="wq101")
    fb.add_argument("--start", default="2021-01-01")
    fb.add_argument("--end", default=None)
    fb.add_argument("--horizons", default="1,5,20,60")
    fb.add_argument("--no-save", action="store_true")
    fb.set_defaults(func=cmd_factors)
    fm = fsub.add_parser("mine")
    fm.add_argument("--population", type=int, default=None)
    fm.add_argument("--generations", type=int, default=None)
    fm.add_argument("--top", type=int, default=10)
    fm.add_argument("--register", action="store_true")
    fm.set_defaults(func=cmd_factors)

    p = sub.add_parser("backtest", help="多因子组合回测")
    p.add_argument("--start", default="2024-01-02")
    p.add_argument("--end", default=None)
    p.add_argument("--train-start", default="2021-01-01")
    p.add_argument("--train-end", default="2023-12-31")
    p.add_argument("--rebalance", type=int, default=21)
    p.add_argument("--top-n", type=int, default=50, dest="top_n")
    p.add_argument("--method", default="ic_weighted", choices=["equal", "ic_weighted"])
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("event", help="T0 事件检测 / 评估")
    p.add_argument("--audit", action="store_true")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("qlib", help="Qlib 导出与校验")
    qsub = p.add_subparsers(dest="qlib_cmd", required=True)
    qv = qsub.add_parser("verify")
    qv.set_defaults(func=cmd_qlib)
    qe = qsub.add_parser("export")
    qe.add_argument("--force", action="store_true")
    qe.set_defaults(func=cmd_qlib)
    qn = qsub.add_parser("native", help="Qlib 原生 LGBM 训练 + Qlib 回测")
    qn.add_argument("--symbols", type=int, default=150)
    qn.add_argument("--topk", type=int, default=50)
    qn.add_argument("--n-drop", type=int, default=5, dest="n_drop")
    qn.add_argument("--no-backtest", action="store_true")
    qn.set_defaults(func=cmd_qlib)

    p = sub.add_parser("web", help="本地 Web 控制台")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("sources", help="iFinD / DataYes 数据源")
    ssub = p.add_subparsers(dest="sources_cmd", required=True)
    st = ssub.add_parser("status")
    st.add_argument("--probe", action="store_true")
    st.set_defaults(func=cmd_sources)
    sp = ssub.add_parser("probe")
    sp.add_argument("--source", required=True, choices=["tushare", "ifind", "datayes"])
    sp.set_defaults(func=cmd_sources)
    sf = ssub.add_parser("fetch")
    sf.add_argument("--source", required=True, choices=["datayes", "ifind"])
    sf.add_argument("--codes", required=True)
    sf.add_argument("--start", required=True)
    sf.add_argument("--end", required=True)
    sf.add_argument("--adjust", default="none", choices=["none", "qfq", "hfq"])
    sf.add_argument("--write", action="store_true")
    sf.set_defaults(func=cmd_sources)

    p = sub.add_parser("demo", help="端到端演示 + HTML 报告")
    p.add_argument("--full", action="store_true")
    p.add_argument("--no-mine", action="store_true")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    try:
        args.func(args, cfg)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
