"""Core correctness tests (stdlib unittest, no external data required)."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from alphaforge.backtest.engine import Broker, run_backtest
from alphaforge.config import load_config
from alphaforge.data.panel import Panel
from alphaforge.evaluate.core import cross_section_ic, gate
from alphaforge.expr import Evaluator
from alphaforge.preprocess import neutralize


def make_panel(T: int = 170, N: int = 24, seed: int = 3) -> Panel:
    rng = np.random.default_rng(seed)
    dates = np.array(pd.bdate_range("2022-01-03", periods=T).strftime("%Y-%m-%d"),
                     dtype="datetime64[D]")
    symbols = [f"S{i:03d}" for i in range(N)]
    ret = rng.normal(0.0005, 0.02, size=(T, N))
    close = 10 * np.exp(np.cumsum(ret, axis=0))
    open_ = close * (1 + rng.normal(0, 0.004, size=(T, N)))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = rng.uniform(1e6, 5e6, size=(T, N))
    amount = close * volume
    prev = np.vstack([close[:1], close[:-1]])
    r = close / prev - 1
    log_mv = np.log(close * 1e9)
    turnover = volume / 1e8
    up = prev * 1.1
    down = prev * 0.9
    data = {
        "close": close.astype(np.float32), "open": open_.astype(np.float32),
        "high": high.astype(np.float32), "low": low.astype(np.float32),
        "volume": volume.astype(np.float32), "amount": amount.astype(np.float32),
        "ret": r.astype(np.float32), "log_mv": log_mv.astype(np.float32),
        "turnover_f": turnover.astype(np.float32),
        "up_limit": up.astype(np.float32), "down_limit": down.astype(np.float32),
        "vwap": ((amount / volume)).astype(np.float32),
        "mkt_ret": np.broadcast_to(np.nanmean(r, axis=1)[:, None], (T, N)).astype(np.float32),
        "listed_days": np.broadcast_to(np.arange(T, dtype=np.float32)[:, None], (T, N)).copy(),
        "is_st": np.zeros((T, N), dtype=np.float32),
        "suspended": np.zeros((T, N), dtype=np.float32),
        "limit_up_flag": np.zeros((T, N), dtype=np.float32),
        "limit_down_flag": np.zeros((T, N), dtype=np.float32),
    }
    masks = {k: np.ones((T, N), dtype=np.uint8) for k in
             ("universe", "tradable", "sellable", "index_member")}
    masks["suspended"] = np.zeros((T, N), dtype=np.uint8)
    masks["limit_up"] = np.zeros((T, N), dtype=np.uint8)
    masks["limit_down"] = np.zeros((T, N), dtype=np.uint8)
    industry = rng.integers(0, 5, size=N).astype(np.int16)
    return Panel(dates=dates, symbols=symbols, data=data, industry_id=industry,
                 industry_names=["a", "b", "c", "d", "e"], masks=masks, meta={})


class TestExpression(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel()
        self.ev = Evaluator(self.panel)

    def test_precedence_and_power(self):
        self.assertTrue(np.allclose(self.ev.eval("1 + 2 * 3"), 7.0))
        self.assertTrue(np.allclose(self.ev.eval("2^3^2"), 512.0))
        self.assertTrue(np.allclose(self.ev.eval("(1+2)*3"), 9.0))

    def test_ts_mean_matches_pandas(self):
        ours = self.ev.eval("ts_mean(close, 10)")
        manual = pd.DataFrame(self.panel.field("close")).rolling(10, min_periods=10).mean().to_numpy()
        # platform uses min_periods=ceil(0.6w)=6; compare only full windows
        mask = np.isfinite(manual)
        self.assertLess(np.nanmax(np.abs(ours[mask] - manual[mask])), 1e-4)

    def test_cs_rank(self):
        ranks = self.ev.eval("cs_rank(ret)")
        row = ranks[-1]
        self.assertAlmostEqual(float(np.nanmean(row)), 0.5, places=2)

    def test_forward_return_alignment(self):
        fwd = self.panel.forward_return(5)
        close = self.panel.field("close")
        t, j = 30, 2
        expected = close[t + 5, j] / close[t, j] - 1
        self.assertAlmostEqual(float(fwd[t, j]), float(expected), places=5)
        self.assertTrue(np.isnan(fwd[-1, j]))

    def test_errors(self):
        with self.assertRaises(Exception):
            self.ev.eval("unknown_field + 1")
        with self.assertRaises(Exception):
            self.ev.eval("ts_mean(close)")


class TestPreprocess(unittest.TestCase):
    def test_neutralize_removes_size(self):
        panel = make_panel()
        rng = np.random.default_rng(1)
        factor = panel.field("log_mv") + rng.normal(0, 1.0, panel.shape)
        out = neutralize(factor, panel, mask=panel.mask("universe"))
        # per-row correlation with size should be near zero
        corrs = []
        for t in range(panel.shape[0]):
            x = out[t]
            y = panel.field("log_mv")[t]
            v = np.isfinite(x) & np.isfinite(y)
            corrs.append(np.corrcoef(x[v], y[v])[0, 1])
        self.assertLess(abs(np.mean(corrs)), 0.05)


class TestBacktest(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel(T=40, N=6)
        self.cfg = load_config()

    def test_limit_up_blocks_buy(self):
        panel = self.panel
        panel.data["up_limit"][5, 0] = panel.data["open"][5, 0]
        broker = Broker(panel, self.cfg)
        self.assertFalse(broker.can_buy(5, 0))
        self.assertTrue(broker.can_buy(5, 1))

    def test_limit_down_blocks_sell(self):
        panel = self.panel
        panel.data["down_limit"][7, 0] = panel.data["open"][7, 0]
        broker = Broker(panel, self.cfg)
        self.assertFalse(broker.can_sell(7, 0))

    def test_backtest_runs_and_respects_next_open(self):
        panel = self.panel
        targets = {3: {panel.symbols[0]: 0.5, panel.symbols[1]: 0.5}}
        bt = run_backtest(panel, targets, cfg=self.cfg,
                          start=str(panel.dates[0]), end=str(panel.dates[-1]))
        self.assertGreater(len(bt.equity), 20)
        if not bt.trades.empty:
            first = bt.trades.iloc[0]
            # signal at index 3 -> first execution at index 4
            self.assertGreaterEqual(first["date"], str(panel.dates[4]))

    def test_t_plus_one(self):
        panel = self.panel
        broker = Broker(panel, self.cfg)
        broker.cash = 1_000_000
        broker.shares[0] = 1000
        broker.buy_idx[0] = 5
        broker.last_price[0] = 10
        # cannot sell on the same day it was bought
        broker._sell(5, 0, 0.0)
        self.assertEqual(broker.shares.get(0), 1000)


class TestEvent(unittest.TestCase):
    def test_detection_and_labels(self):
        from alphaforge.event.dataset import build_event_dataset

        panel = make_panel(T=200, N=12, seed=5)
        # create a clear volume/price surge on day 100 for symbol 0
        panel.data["volume"][140, 0] *= 15
        panel.data["amount"][140, 0] = panel.data["close"][140, 0] * panel.data["volume"][140, 0]
        panel.data["ret"][140, 0] = 0.12
        panel.data["close"][140, 0] = panel.data["close"][139, 0] * 1.12
        panel.data["turnover_f"][140, 0] = 0.20
        ds = build_event_dataset(panel, factor_names=["ret_5", "volatility_20"])
        self.assertGreater(len(ds.events), 0)
        row = ds.events[(ds.events["code"] == "S000") & (ds.events["t0_idx"] == 140)]
        self.assertGreaterEqual(len(row), 1)
        self.assertIn(row.iloc[0]["tier"], ("strong", "weak", "negative"))
        self.assertLess(int(row.iloc[0]["asof_idx"]), int(row.iloc[0]["t0_idx"]))

    def test_ic_sign(self):
        panel = make_panel(T=120, N=30)
        # factor = next return -> should have strong positive IC
        fwd = panel.forward_return(5)
        f = fwd.copy()
        valid = np.isfinite(f) & panel.mask("universe")
        ic = cross_section_ic(f, fwd, valid, panel.dates, min_names=10)
        self.assertGreater(float(ic.mean()), 0.99)


class TestWQ101(unittest.TestCase):
    def test_translation_and_parse(self):
        from alphaforge.expr.wq101 import translate_all, wq101_defs

        translated = translate_all()
        self.assertEqual(len(translated), 101)
        self.assertIn("ts_mean(amount, 20)", translated[7])
        self.assertIn("cs_indneutralize", translated[48])
        from alphaforge.expr.parser import parse

        self.assertIn("where(", parse(translated[9]).to_string())
        defs = wq101_defs()
        self.assertEqual(len(defs), 101)
        self.assertTrue(all(d.category == "wq101" for d in defs))

    def test_sample_evaluation(self):
        from alphaforge.expr.library import get_factor
        from alphaforge.expr import Evaluator

        panel = make_panel(T=120, N=20, seed=11)
        ev = Evaluator(panel, mask="universe")
        arr = ev.eval(get_factor("wq101").expression)  # simplest formula
        self.assertEqual(arr.shape, panel.shape)
        self.assertGreater(np.isfinite(arr).sum(), 0)


class TestGate(unittest.TestCase):
    def test_reject_weak_factor(self):
        cfg = load_config()
        primary = {"mean": 0.001, "mean_monthly": 0.001, "icir": 0.01,
                   "icir_monthly": 0.01, "hit_rate": 0.5, "hit_rate_monthly": 0.5,
                   "n": 100, "n_months": 10}
        qsum = {"monotonicity": 0.1, "long_short": {"directional_net_annualized": -0.01}}
        out = gate(primary, qsum, coverage_value=0.8, cfg=cfg)
        self.assertEqual(out["verdict"], "REJECT")


if __name__ == "__main__":
    unittest.main()
