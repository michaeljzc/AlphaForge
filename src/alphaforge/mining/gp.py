"""Genetic-programming factor mining.

The engine evolves expression trees over the same DSL used by hand-written
factors, scores them by cross-sectional RankIC on a training window, and
reports validation/test decay.  It deliberately keeps the fitness pipeline
simple (rank IC + parsimony) and pushes neutralisation, cost and gate checks to
the full evaluation stage, so the search cannot overfit to expensive
preprocessing artefacts.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.evaluate.core import cross_section_ic, evaluate_factor, rank_pct
from alphaforge.expr import Evaluator
from alphaforge.expr.ast import Node
from alphaforge.expr.library import FactorDef
from alphaforge.mining.registry import FactorRegistry
from alphaforge.utils import write_json

WINDOWS = [5, 10, 20, 60]

# (name, kind) -- kind drives how the random tree fills arguments
FUNCS: list[tuple[str, str]] = [
    ("add", "bin"), ("sub", "bin"), ("mul", "bin"), ("div", "bin"),
    ("neg", "un"), ("abs", "un"), ("log", "un"), ("sign", "un"),
    ("ts_mean", "ts1"), ("ts_std", "ts1"), ("ts_max", "ts1"), ("ts_min", "ts1"),
    ("ts_rank", "ts1"), ("delta", "ts1"), ("ts_decay_linear", "ts1"),
    ("ts_zscore", "ts1"), ("ts_ir", "ts1"), ("ts_skew", "ts1"),
    ("ts_corr", "ts2"), ("cs_rank", "cs"), ("cs_zscore", "cs"),
]

DEFAULT_FIELDS = [
    "open", "high", "low", "close", "volume", "amount", "vwap", "ret",
    "turnover_f", "volume_ratio", "pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv",
    "log_mv", "main_net_ratio", "net_mf_ratio", "earnings_yield", "book_to_price",
    "roe", "netprofit_yoy", "or_yoy", "grossprofit_margin", "debt_to_assets",
    "limit_up_flag", "mkt_ret", "free_turnover",
]

CONSTS = [1.0, 2.0, 5.0, 10.0, 0.5]


@dataclass
class GPConfig:
    population: int = 200
    generations: int = 15
    tournaments: int = 3
    crossover_rate: float = 0.6
    mutation_rate: float = 0.3
    max_depth: int = 4
    max_nodes: int = 28
    parsimony: float = 0.0002
    hall_of_fame: int = 30
    seed: int = 42
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    horizon: int = 5
    train_start: str = "2021-01-01"
    train_end: str = "2023-12-31"
    valid_start: str = "2024-01-01"
    valid_end: str = "2024-12-31"
    test_start: str = "2025-01-01"
    test_end: str = "2026-10-31"
    sample_symbols: int = 300
    eval_step: int = 2

    @classmethod
    def from_config(cls, cfg: Config) -> "GPConfig":
        gp = cfg.get("mining.gp", {}) or {}
        base = cls()
        for key, value in gp.items():
            if hasattr(base, key) and value is not None:
                setattr(base, key, value)
        return base


@dataclass
class Individual:
    node: Node
    fitness: float = -1e9
    ic: float = float("nan")
    icir: float = float("nan")
    n: int = 0
    coverage: float = float("nan")
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def expression(self) -> str:
        return self.node.to_string()


class FitnessEvaluator:
    def __init__(self, panel: Panel, cfg: GPConfig):
        self.cfg = cfg
        rng = np.random.default_rng(cfg.seed)
        T, N = panel.shape
        valid_counts = np.isfinite(panel.field("close")).sum(axis=0)
        n_keep = min(cfg.sample_symbols, N)
        keep = np.argsort(-valid_counts)[:n_keep]
        symbols = [panel.symbols[i] for i in sorted(keep)]
        self.sub = panel.slice(None, cfg.train_end, symbols=symbols)
        self.ev = Evaluator(self.sub, mask="universe", cache_mb=384)
        self.fwd = self.sub.forward_return(cfg.horizon)
        date_mask = self.sub.date_mask(cfg.train_start, cfg.train_end)[:, None]
        self.mask = self.sub.mask("universe") & date_mask
        self.cache: dict[str, dict[str, Any]] = {}
        self.n_evals = 0
        # style controls for the quick neutralisation used inside fitness:
        # a mined factor must add information beyond size / price / turnover
        self.styles = [self.sub.field("log_mv"), self.sub.field("close"),
                       self.sub.field("turnover_f")]

    def evaluate(self, node: Node) -> dict[str, Any]:
        expr = node.to_string()
        if expr in self.cache:
            return self.cache[expr]
        self.n_evals += 1
        try:
            arr = self.ev.eval(node)
        except Exception as exc:
            out = {"fitness": -1e9, "ic": float("nan"), "icir": float("nan"),
                   "n": 0, "coverage": 0.0, "error": str(exc)[:120]}
            self.cache[expr] = out
            return out
        finite = np.isfinite(arr)
        cov = float(finite[self.mask].mean()) if self.mask.any() else 0.0
        if cov < 0.25:
            out = {"fitness": -1e9, "ic": float("nan"), "icir": float("nan"),
                   "n": 0, "coverage": cov}
            self.cache[expr] = out
            return out
        neutral = self._quick_neutral(arr)
        ic_series = cross_section_ic(neutral, self.fwd, self.mask, self.sub.dates,
                                     min_names=30)
        if len(ic_series) < 50:
            out = {"fitness": -1e9, "ic": float("nan"), "icir": float("nan"),
                   "n": len(ic_series), "coverage": cov}
            self.cache[expr] = out
            return out
        ic = float(ic_series.mean())
        std = float(ic_series.std(ddof=1))
        icir = ic / std if std > 1e-12 else float("nan")
        fitness = abs(ic) + 0.05 * abs(icir) - self.cfg.parsimony * node.size()
        if node.size() > self.cfg.max_nodes or node.depth() > self.cfg.max_depth:
            fitness = -1e9
        out = {"fitness": fitness, "ic": ic, "icir": icir, "n": len(ic_series),
               "coverage": cov, "size": node.size(), "depth": node.depth()}
        self.cache[expr] = out
        return out


    def _quick_neutral(self, arr: np.ndarray) -> np.ndarray:
        valid = self.mask & np.isfinite(arr)
        f = rank_pct(np.asarray(arr, dtype=np.float64), valid)
        X = [np.ones_like(f), rank_pct(self.styles[0].astype(np.float64), valid),
             rank_pct(self.styles[1].astype(np.float64), valid),
             rank_pct(self.styles[2].astype(np.float64), valid)]
        design = np.stack(X, axis=-1)
        out = np.full_like(f, np.nan)
        for t in range(f.shape[0]):
            v = valid[t]
            n = int(v.sum())
            if n < 30:
                continue
            y = f[t][v]
            xt = design[t][v]
            try:
                beta, *_ = np.linalg.lstsq(xt, y, rcond=None)
            except np.linalg.LinAlgError:
                continue
            out[t][v] = y - xt @ beta
        return out

# --------------------------------------------------------------------------
# tree utilities
# --------------------------------------------------------------------------
def paths(node: Node, prefix: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], Node]]:
    out = [(prefix, node)]
    for i, child in enumerate(node.args):
        out.extend(paths(child, prefix + (i,)))
    return out


def get_at(node: Node, path: tuple[int, ...]) -> Node:
    for i in path:
        node = node.args[i]
    return node


def set_at(node: Node, path: tuple[int, ...], new: Node) -> Node:
    if not path:
        return new
    i = path[0]
    args = list(node.args)
    args[i] = set_at(args[i], path[1:], new)
    return Node(kind=node.kind, name=node.name, value=node.value, args=tuple(args))


class GP:
    def __init__(self, panel: Panel, cfg: GPConfig, gp_config: Config | None = None):
        self.panel = panel
        self.cfg = cfg
        self.project_cfg = gp_config
        self.rng = random.Random(cfg.seed)
        self.fitness = FitnessEvaluator(panel, cfg)
        self.t0 = time.time()

    # -- random tree -------------------------------------------------------
    def _leaf(self) -> Node:
        if self.rng.random() < 0.85:
            return Node.field(self.rng.choice(self.cfg.fields))
        return Node.const(self.rng.choice(CONSTS))

    def _window(self) -> Node:
        return Node.const(float(self.rng.choice(WINDOWS)))

    def random_tree(self, depth: int = 0) -> Node:
        if depth >= self.cfg.max_depth or (depth > 0 and self.rng.random() < 0.25):
            return self._leaf()
        name, kind = self.rng.choice(FUNCS)
        if kind == "bin":
            return Node.op(name, self.random_tree(depth + 1), self.random_tree(depth + 1))
        if kind == "un":
            return Node.op(name, self.random_tree(depth + 1))
        if kind == "cs":
            return Node.op(name, self.random_tree(depth + 1))
        if kind == "ts1":
            return Node.op(name, self.random_tree(depth + 1), self._window())
        if kind == "ts2":
            return Node.op(name, self.random_tree(depth + 1),
                           self.random_tree(depth + 1), self._window())
        raise ValueError(kind)

    def _valid(self, node: Node) -> bool:
        return (node.size() <= self.cfg.max_nodes and node.depth() <= self.cfg.max_depth
                and len(node.fields()) > 0)

    # -- operators ---------------------------------------------------------
    def crossover(self, a: Node, b: Node) -> Node:
        for _ in range(10):
            pa = self.rng.choice(paths(a)[1:])[0] if len(paths(a)) > 1 else ()
            pb = self.rng.choice(paths(b))[0]
            child = set_at(a, pa, get_at(b, pb))
            if self._valid(child):
                return child
        return a

    def mutate(self, node: Node) -> Node:
        for _ in range(10):
            ps = self.rng.choice(paths(node))[0]
            new = self.random_tree(depth=len(ps))
            child = set_at(node, ps, new)
            if self._valid(child):
                return child
        return node

    def tournament(self, pop: list[Individual]) -> Individual:
        k = min(self.cfg.tournaments, len(pop))
        return max(self.rng.sample(pop, k), key=lambda x: x.fitness)

    # -- main loop ---------------------------------------------------------
    def run(self, verbose: bool = True) -> dict[str, Any]:
        pop = [Individual(self.random_tree()) for _ in range(self.cfg.population)]
        # dedupe
        seen = {}
        for ind in pop:
            seen.setdefault(ind.expression, ind)
        pop = list(seen.values())
        while len(pop) < self.cfg.population:
            t = self.random_tree()
            if t.to_string() not in seen:
                seen[t.to_string()] = Individual(t)
                pop.append(seen[t.to_string()])

        for ind in pop:
            self._score(ind)
        pop.sort(key=lambda x: x.fitness, reverse=True)
        history = []
        for gen in range(self.cfg.generations):
            elite = pop[: max(2, int(0.1 * len(pop)))]
            newpop = list(elite)
            seen = {ind.expression for ind in newpop}
            while len(newpop) < self.cfg.population:
                parent = self.tournament(pop)
                if self.rng.random() < self.cfg.crossover_rate:
                    other = self.tournament(pop)
                    child_node = self.crossover(parent.node, other.node)
                else:
                    child_node = parent.node
                if self.rng.random() < self.cfg.mutation_rate:
                    child_node = self.mutate(child_node)
                expr = child_node.to_string()
                if expr in seen or not self._valid(child_node):
                    continue
                child = Individual(child_node)
                self._score(child)
                newpop.append(child)
                seen.add(expr)
            pop = newpop
            pop.sort(key=lambda x: x.fitness, reverse=True)
            best = pop[0]
            history.append({"generation": gen, "best_fitness": best.fitness,
                            "best_ic": best.ic, "best_expression": best.expression,
                            "evaluations": self.fitness.n_evals})
            if verbose:
                print(f"[gp] gen {gen:02d} fitness={best.fitness:.4f} "
                      f"|IC|={abs(best.ic):.4f} size={best.node.size()} "
                      f"evals={self.fitness.n_evals} expr={best.expression[:70]}")

        # hall of fame with correlation-aware diversity
        hof = self._hall_of_fame(pop)
        result = {
            "config": self.cfg.__dict__,
            "elapsed_sec": round(time.time() - self.t0, 1),
            "evaluations": self.fitness.n_evals,
            "history": history,
            "hall_of_fame": [self._candidate_dict(ind) for ind in hof],
        }
        return result

    def _score(self, ind: Individual) -> None:
        m = self.fitness.evaluate(ind.node)
        ind.fitness = float(m.get("fitness", -1e9))
        ind.ic = float(m.get("ic", float("nan")))
        ind.icir = float(m.get("icir", float("nan")))
        ind.n = int(m.get("n", 0))
        ind.coverage = float(m.get("coverage", 0.0))
        ind.metrics = m

    def _hall_of_fame(self, pop: list[Individual]) -> list[Individual]:
        hof: list[Individual] = []
        arrays: dict[str, np.ndarray] = {}
        for ind in pop:
            if ind.fitness <= -1e8:
                continue
            try:
                arr = self.fitness.ev.eval(ind.node)
            except Exception:
                continue
            redundant = False
            for prev in arrays.values():
                v = np.isfinite(arr) & np.isfinite(prev)
                if v.sum() < 100:
                    continue
                # sample rows for speed
                idx = np.linspace(0, arr.shape[0] - 1, min(200, arr.shape[0])).astype(int)
                a = arr[idx][v[idx]]
                b = prev[idx][v[idx]]
                if a.size > 10 and np.std(a) > 0 and np.std(b) > 0:
                    c = abs(float(np.corrcoef(a, b)[0, 1]))
                    if c > 0.70:
                        redundant = True
                        break
            if redundant:
                continue
            hof.append(ind)
            arrays[ind.expression] = arr
            if len(hof) >= self.cfg.hall_of_fame:
                break
        return hof

    def _candidate_dict(self, ind: Individual) -> dict[str, Any]:
        return {
            "expression": ind.expression,
            "fitness": ind.fitness,
            "train_ic": ind.ic,
            "train_icir": ind.icir,
            "train_n": ind.n,
            "coverage": ind.coverage,
            "size": ind.node.size(),
            "depth": ind.node.depth(),
        }


def evaluate_candidates(panel: Panel, candidates: list[dict[str, Any]],
                        cfg: Config, top: int = 12) -> list[dict[str, Any]]:
    """Full evaluation (preprocess + gate) of GP winners on valid/test windows."""
    out = []
    for cand in candidates[:top]:
        expr = cand["expression"]
        row = dict(cand)
        for label, (start, end) in {
            "train": (cfg.get("mining.gp.train_start", "2021-01-01"),
                      cfg.get("mining.gp.train_end", "2023-12-31")),
            "valid": (cfg.get("mining.gp.valid_start", "2024-01-01"),
                      cfg.get("mining.gp.valid_end", "2024-12-31")),
            "test": (cfg.get("mining.gp.test_start", "2025-01-01"),
                     cfg.get("mining.gp.test_end", "2026-10-31")),
        }.items():
            try:
                rep = evaluate_factor(panel, expr, name=f"gp_{label}", cfg=cfg,
                                      start=start, end=end, horizons=[5, 20])
                p = rep.ic[5]
                row[f"{label}_ic"] = p.get("mean")
                row[f"{label}_icir"] = p.get("icir")
                row[f"{label}_monthly_ic"] = p.get("mean_monthly")
                if label == "valid":
                    row["valid_verdict"] = rep.verdict
                    row["valid_mono"] = rep.quantile.get("monotonicity")
            except Exception as exc:
                row[f"{label}_error"] = str(exc)[:120]
        out.append(row)
    return out


def run_gp(panel: Panel, cfg: Config | None = None, save: bool = True,
           register: bool = False, population: int | None = None,
           generations: int | None = None, top_eval: int = 10) -> dict[str, Any]:
    cfg = cfg or load_config()
    gp_cfg = GPConfig.from_config(cfg)
    if population:
        gp_cfg.population = int(population)
    if generations:
        gp_cfg.generations = int(generations)
    engine = GP(panel, gp_cfg, cfg)
    result = engine.run()
    result["evaluated"] = evaluate_candidates(panel, result["hall_of_fame"], cfg, top=top_eval)
    if save:
        path = cfg.paths.factors / f"gp_run_{time.strftime('%Y%m%d_%H%M%S')}.json"
        write_json(path, result)
        write_json(cfg.paths.factors / "gp_latest.json", result)
        result["path"] = str(path)
    if register:
        reg = FactorRegistry(cfg)
        for i, cand in enumerate(result["evaluated"]):
            reg.add(name=f"gp_{i:02d}", expression=cand["expression"],
                    category="mined", direction=1,
                    metrics={k: v for k, v in cand.items() if k != "expression"},
                    source="gp", notes=str(cand.get("valid_verdict", "")))
    return result
