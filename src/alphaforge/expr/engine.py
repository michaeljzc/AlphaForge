"""Expression evaluator with an LRU-ish result cache.

The evaluator is the only component that turns an expression string into a
``(T, N)`` array.  It is used by factor evaluation, GP mining, portfolio
construction and the event layer, guaranteeing identical semantics everywhere.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from alphaforge.data.panel import Panel
from alphaforge.expr.ast import Node, node_from_string
from alphaforge.expr.ops import EvalContext, OPS


class ExpressionError(RuntimeError):
    pass


class Evaluator:
    def __init__(self, panel: Panel, mask: np.ndarray | str | None = None,
                 dtype: np.dtype = np.float32, cache_mb: float = 512.0):
        if isinstance(mask, str):
            mask = panel.mask(mask)
        if mask is not None:
            mask = np.asarray(mask, dtype=bool)
            if mask.shape != panel.shape:
                raise ValueError(f"mask 形状 {mask.shape} 与面板 {panel.shape} 不一致")
        self.panel = panel
        self.ctx = EvalContext(panel.shape, mask, np.dtype(dtype), panel.industry_id)
        self.cache: dict[str, np.ndarray] = {}
        self.cache_bytes = 0
        self.cache_limit = int(cache_mb * 1024 * 1024)
        self.n_calls = 0

    # -- public ------------------------------------------------------------
    def eval(self, expr: str | Node) -> np.ndarray:
        node = node_from_string(expr) if isinstance(expr, str) else expr
        out = self._eval(node)
        if not isinstance(out, np.ndarray):
            out = np.full(self.panel.shape, float(out), dtype=self.ctx.dtype)
        if out.ndim == 1:
            out = out[:, None]
        if out.shape != self.panel.shape:
            if out.shape[0] == self.panel.shape[0] and out.shape[1] == 1:
                out = np.repeat(out, self.panel.shape[1], axis=1)
            else:
                out = np.broadcast_to(out, self.panel.shape)
        return np.asarray(out, dtype=self.ctx.dtype)

    def frame(self, expr: str | Node) -> pd.DataFrame:
        return pd.DataFrame(self.eval(expr), index=pd.DatetimeIndex(self.panel.dates),
                            columns=self.panel.symbols)

    # -- internals ---------------------------------------------------------
    def _eval(self, node: Node) -> np.ndarray | float:
        if node.kind == "const":
            return node.value
        if node.kind == "field":
            return self._field(node.name)
        key = node.to_string()
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        args = [self._eval(a) for a in node.args]
        op = OPS.get(node.name)
        if op is None:
            raise ExpressionError(f"未知算子 {node.name}")
        try:
            out = op.func(self.ctx, *args)
        except Exception as exc:
            raise ExpressionError(f"计算 {key} 失败: {exc}") from exc
        if isinstance(out, np.ndarray):
            if out.ndim == 1:
                out = out[:, None]
            if out.shape != self.panel.shape:
                if out.shape[0] == self.panel.shape[0] and out.shape[1] == 1:
                    out = np.repeat(out, self.panel.shape[1], axis=1)
                else:
                    out = np.broadcast_to(out, self.panel.shape)
            out = np.ascontiguousarray(out, dtype=self.ctx.dtype)
            self._store(key, out)
        self.n_calls += 1
        return out

    def _field(self, name: str) -> np.ndarray:
        try:
            return self.panel.field(name)
        except KeyError as exc:
            raise ExpressionError(str(exc)) from exc

    def _store(self, key: str, arr: np.ndarray) -> None:
        nbytes = arr.nbytes
        if nbytes > self.cache_limit / 4:
            return
        if self.cache_bytes + nbytes > self.cache_limit:
            # drop the oldest half (insertion ordered dict)
            for k in list(self.cache)[: max(1, len(self.cache) // 2)]:
                self.cache_bytes -= self.cache.pop(k).nbytes
        old = self.cache.get(key)
        if old is not None:
            self.cache_bytes -= old.nbytes
        self.cache[key] = arr
        self.cache_bytes += nbytes


# --------------------------------------------------------------------------
# module level helpers
# --------------------------------------------------------------------------
def make_evaluator(panel: Panel, mask: np.ndarray | str | None = "universe",
                   cache_mb: float = 512.0) -> Evaluator:
    return Evaluator(panel, mask=mask, cache_mb=cache_mb)


def evaluate(expr: str | Node, panel: Panel, mask: np.ndarray | str | None = None,
             evaluator: Evaluator | None = None) -> np.ndarray:
    ev = evaluator or Evaluator(panel, mask=mask)
    return ev.eval(expr)


def evaluate_frame(expr: str | Node, panel: Panel, mask: np.ndarray | str | None = None,
                   evaluator: Evaluator | None = None) -> pd.DataFrame:
    return pd.DataFrame(evaluate(expr, panel, mask, evaluator),
                        index=pd.DatetimeIndex(panel.dates), columns=panel.symbols)


def validate(expr: str | Node, panel: Panel | None = None) -> dict[str, Any]:
    node = node_from_string(expr) if isinstance(expr, str) else expr
    fields = sorted(node.fields())
    missing = []
    if panel is not None:
        missing = [f for f in fields if not panel.has(f)]
    return {
        "expression": node.to_string(),
        "fields": fields,
        "missing_fields": missing,
        "operators": sorted(set(node.operators())),
        "size": node.size(),
        "depth": node.depth(),
    }


def evaluate_batch(exprs: Sequence[str], panel: Panel, mask: np.ndarray | str | None = "universe",
                   cache_mb: float = 512.0) -> dict[str, np.ndarray]:
    ev = Evaluator(panel, mask=mask, cache_mb=cache_mb)
    out: dict[str, np.ndarray] = {}
    for expr in exprs:
        out[expr] = ev.eval(expr)
    return out


def benchmark(panel: Panel, exprs: Iterable[str], mask: str = "universe") -> pd.DataFrame:
    rows = []
    ev = Evaluator(panel, mask=mask)
    for expr in exprs:
        t0 = time.perf_counter()
        arr = ev.eval(expr)
        rows.append({"expression": expr, "seconds": round(time.perf_counter() - t0, 3),
                     "coverage": float(np.isfinite(arr).mean())})
    return pd.DataFrame(rows)
