"""Qlib-native model training and backtest (Qlib as the runtime, not just the format).

What is Qlib here
-----------------
* ``qlib.contrib.model.gbdt.LGBModel`` for training / prediction
* ``qlib.workflow.R`` (MLflow recorder) for the experiment record
* ``qlib.contrib.strategy.TopkDropoutStrategy`` + ``qlib.backtest.backtest``
  + ``SimulatorExecutor`` for the native Qlib backtest
* Qlib binary data (``data/qlib_cn``) as the provider, including the
  ``SH000300`` benchmark.

The Alpha158 feature *values* are computed by AlphaForge's fast vectorised
engine and served to Qlib through a ``DatasetH``-compatible object, because
Qlib's per-instrument ``Alpha158`` handler takes >10 minutes on 1,000+
instruments.  The model, recorder, strategy and executor are Qlib's own code.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel, load_panel
from alphaforge.data.qlib_export import qlib_init, qlib_symbol
from alphaforge.expr import Evaluator
from alphaforge.expr.library import alpha158_factors


@dataclass
class NativeDataset:
    df: pd.DataFrame
    segments: dict[str, tuple[str, str]]
    feature_names: list[str]
    symbols: list[str]

    def prepare(self, segment: str, col_set: Any = None, data_key: Any = None,
                **kwargs) -> pd.DataFrame:
        start, end = self.segments[segment]
        sub = self.df.loc[(slice(pd.Timestamp(start), pd.Timestamp(end)), slice(None)), :]
        if col_set is None:
            return sub
        if isinstance(col_set, str):
            col_set = [col_set]
        return sub.loc[:, col_set]


def _select_symbols(panel: Panel, n: int) -> list[str]:
    coverage = np.isfinite(panel.field("close")).sum(axis=0)
    order = np.argsort(-coverage)
    picked = sorted(int(i) for i in order[: min(n, panel.shape[1])])
    return [panel.symbols[i] for i in picked]


def build_dataset(panel: Panel, n_symbols: int = 150, start: str = "2021-01-01",
                  end: str = "2026-10-30", train_end: str = "2023-12-31",
                  valid_end: str = "2024-12-31", horizon: int = 5,
                  factors: Sequence | None = None, verbose: bool = True) -> NativeDataset:
    t0 = time.time()
    factors = list(factors or alpha158_factors())
    symbols = _select_symbols(panel, n_symbols)
    sub = panel.slice(None, end, symbols=symbols)
    ev = Evaluator(sub, mask="universe", cache_mb=1024)
    date_mask = sub.date_mask(start, end)
    dates = sub.dates[date_mask]
    n_dates = len(dates)
    N = len(symbols)
    cols = np.empty((n_dates * N, len(factors)), dtype=np.float32)
    for k, f in enumerate(factors):
        arr = ev.eval(f.expression)
        cols[:, k] = np.asarray(arr[date_mask], dtype=np.float32).ravel()
        if verbose and (k + 1) % 20 == 0:
            print(f"[qlib-native] features {k+1}/{len(factors)} {time.time()-t0:.0f}s", flush=True)
    index = pd.MultiIndex.from_product(
        [pd.DatetimeIndex(dates), [qlib_symbol(c) for c in symbols]],
        names=["datetime", "instrument"])
    feature_cols = pd.MultiIndex.from_tuples(
        [("feature", f.name) for f in factors], names=["group", "name"])
    features = pd.DataFrame(cols, index=index, columns=feature_cols)

    fwd = sub.forward_return(horizon, lag=1)[date_mask]
    labels = pd.DataFrame(fwd.ravel().astype(np.float32), index=index,
                          columns=pd.MultiIndex.from_tuples([("label", "LABEL0")],
                                                            names=["group", "name"]))
    df = pd.concat([features, labels], axis=1)
    df = df[np.isfinite(df[("label", "LABEL0")].to_numpy())]
    segments = {
        "train": (start, train_end),
        "valid": (train_end, valid_end),
        "test": (valid_end, end),
    }
    if verbose:
        print(f"[qlib-native] dataset {df.shape} symbols={N} dates={n_dates} "
              f"features={len(factors)} {time.time()-t0:.0f}s", flush=True)
    return NativeDataset(df=df, segments=segments, feature_names=[f.name for f in factors],
                         symbols=symbols)


def run_qlib_native(cfg: Config | None = None, n_symbols: int = 150, topk: int = 50,
                    n_drop: int = 5, horizon: int = 5, save: bool = True,
                    run_backtest: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config()
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    qlib_init(cfg)

    from qlib.contrib.eva.alpha import calc_ic
    from qlib.contrib.evaluate import risk_analysis
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.workflow import R

    panel = load_panel(cfg)
    t0 = time.time()
    dataset = build_dataset(panel, n_symbols=n_symbols, horizon=horizon,
                            start="2021-01-01", end=cfg.data_end,
                            train_end="2023-12-31", valid_end="2024-12-31")
    model = LGBModel(
        loss="mse", learning_rate=0.03, num_leaves=31, min_data_in_leaf=200,
        feature_fraction=0.75, bagging_fraction=0.8, bagging_freq=1,
        lambda_l2=1.0, early_stopping_rounds=50, num_boost_round=600,
        verbosity=-1,
    )
    with R.start(experiment_name="alphaforge_qlib_native"):
        model.fit(dataset, verbose_eval=100)
        pred = model.predict(dataset, segment="test")
        R.save_objects(model=model)
    print(f"[qlib-native] model fitted {time.time()-t0:.0f}s", flush=True)

    result: dict[str, Any] = {
        "config": {"n_symbols": n_symbols, "topk": topk, "n_drop": n_drop,
                   "horizon": horizon, "segments": dataset.segments},
        "dataset": {"rows": int(len(dataset.df)), "symbols": len(dataset.symbols),
                    "features": len(dataset.feature_names)},
        "pred": {"n": int(len(pred)), "start": str(pred.index.get_level_values(0).min()),
                 "end": str(pred.index.get_level_values(0).max())},
    }

    # ---- IC on the Qlib test segment -----------------------------------
    label = dataset.prepare("test", col_set="label")
    ic, ric = calc_ic(pred, label.iloc[:, 0] if isinstance(label, pd.DataFrame) else label)
    ic = pd.Series(ic).dropna()
    ric = pd.Series(ric).dropna()
    monthly = ic.copy()
    monthly.index = pd.to_datetime(monthly.index)
    mm = monthly.resample("ME").mean().dropna()
    result["ic"] = {
        "n": int(len(ic)), "mean": float(ic.mean()), "std": float(ic.std(ddof=1)),
        "icir": float(ic.mean() / ic.std(ddof=1)) if ic.std(ddof=1) else float("nan"),
        "rank_mean": float(ric.mean()),
        "rank_icir": float(ric.mean() / ric.std(ddof=1)) if ric.std(ddof=1) else float("nan"),
        "monthly_mean": float(mm.mean()) if len(mm) else float("nan"),
        "monthly_icir": float(mm.mean() / mm.std(ddof=1)) if len(mm) > 1 and mm.std(ddof=1) else float("nan"),
        "months": int(len(mm)),
        "positive_rate": float((ic > 0).mean()),
        "series": {"dates": [str(d.date()) for d in pd.to_datetime(ic.index)],
                   "values": [float(v) for v in ic.to_numpy()]},
    }

    # ---- Qlib native backtest ------------------------------------------
    if run_backtest:
        try:
            from qlib.backtest import backtest
            from qlib.contrib.strategy import TopkDropoutStrategy

            strategy = TopkDropoutStrategy(signal=pred, topk=topk, n_drop=n_drop,
                                           hold_thresh=1, only_tradable=True,
                                           forbid_all_trade_at_limit=True)
            executor = {
                "class": "SimulatorExecutor", "module_path": "qlib.backtest.executor",
                "kwargs": {"time_per_step": "day", "generate_portfolio_metrics": True},
            }
            exchange_kwargs = {
                "freq": "day", "limit_threshold": 0.095, "deal_price": "close",
                "open_cost": 0.0005, "close_cost": 0.0015, "min_cost": 5,
                "trade_unit": 100,
            }
            # Qlib's calendar slice looks one step ahead; avoid the final bar
            bt_end = min(str(cfg.data_end), "2026-10-29")
            pm, indicator = backtest(
                start_time="2025-01-02", end_time=bt_end,
                strategy=strategy, executor=executor, benchmark="SH000300",
                account=100_000_000, exchange_kwargs=exchange_kwargs,
            )
            entry = pm.get("1day", pm)
            daily = entry[0] if isinstance(entry, tuple) else entry
            ret = daily["return"]
            bench = daily.get("bench")
            cost = daily.get("cost")
            turnover = daily.get("turnover")
            eq = (1 + ret).fillna(0).cumprod()
            years = max(len(ret) / 252.0, 1e-9)
            cagr = float(eq.iloc[-1] ** (1 / years) - 1)
            vol = float(ret.std() * np.sqrt(252))
            sharpe = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else float("nan")
            mdd = float((eq / eq.cummax() - 1).min())
            excess = (ret - bench).dropna() if bench is not None else ret.dropna()
            ir = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else float("nan")
            analysis = {}
            if bench is not None:
                try:
                    analysis = risk_analysis(ret - bench, freq="day")
                except Exception:
                    analysis = {}
            result["qlib_backtest"] = {
                "annualized_return": cagr,
                "information_ratio": ir,
                "max_drawdown": mdd,
                "sharpe": sharpe,
                "volatility": vol,
                "total_return": float(eq.iloc[-1] - 1),
                "benchmark_return": float((1 + bench).prod() - 1) if bench is not None else None,
                "turnover": float(turnover.mean()) if turnover is not None else None,
                "cost": float(cost.sum()) if cost is not None else None,
                "n_days": int(len(ret)),
            }
            result["qlib_backtest"]["equity"] = [float(x) for x in eq.to_numpy()]
            result["qlib_backtest"]["benchmark_equity"] = (
                [float(x) for x in (1 + bench).fillna(0).cumprod().to_numpy()]
                if bench is not None else [])
            result["qlib_backtest"]["dates"] = [str(d.date()) for d in ret.index]
            R.log_metrics(**{k: v for k, v in result["qlib_backtest"].items()
                             if isinstance(v, (int, float))})
        except Exception as exc:
            import traceback
            result["qlib_backtest"] = {"error": str(exc)[:400],
                                       "traceback": traceback.format_exc()[-1500:]}
            print(f"[qlib-native] backtest failed: {exc}", flush=True)

    # ---- feed Qlib predictions into AlphaForge's A-share backtester -----
    try:
        from alphaforge.backtest.engine import run_backtest
        from alphaforge.portfolio.combine import build_targets

        scores = np.full(panel.shape, np.nan, dtype=np.float32)
        code_map = {s: i for i, s in enumerate(panel.symbols)}
        for dt, inst in pred.index:
            code = str(inst)[2:]
            if code in code_map:
                t = panel.date_index(str(dt.date()), strict=False)
                scores[t, code_map[code]] = float(pred.loc[(dt, inst)])
        targets = build_targets(panel, scores, cfg=cfg, start="2025-01-01",
                                end=cfg.data_end, rebalance_days=1, top_n=topk)
        bt = run_backtest(panel, targets, cfg=cfg, start="2025-01-02", end=cfg.data_end)
        result["alphaforge_backtest"] = bt.metrics
        result["alphaforge_backtest"]["n_targets"] = len(targets)
    except Exception as exc:
        result["alphaforge_backtest"] = {"error": str(exc)[:400]}

    result["elapsed_sec"] = round(time.time() - t0, 1)
    if save:
        from alphaforge.utils import write_json
        write_json(cfg.paths.reports / "artifacts" / "qlib_native.json", result)
    return result


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Qlib-native LGBM training + backtest")
    ap.add_argument("--config", default=None)
    ap.add_argument("--symbols", type=int, default=150)
    ap.add_argument("--topk", type=int, default=50)
    ap.add_argument("--n-drop", type=int, default=5)
    ap.add_argument("--no-backtest", action="store_true")
    args = ap.parse_args(argv)
    res = run_qlib_native(load_config(args.config), n_symbols=args.symbols,
                          topk=args.topk, n_drop=args.n_drop,
                          run_backtest=not args.no_backtest)
    import json

    print(json.dumps(res, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()
