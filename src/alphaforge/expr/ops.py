"""Vectorised operator library for factor expressions.

All operators work on ``(T, N)`` arrays (dates x symbols) and are deliberately
NaN-aware.  Three families exist:

* elementwise   -- broadcasting arithmetic / math
* cross-section -- applied per date (axis=1)
* time-series   -- rolling windows (axis=0)

Windows are causal: a value at row ``t`` only uses rows ``<= t``.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


@dataclass(frozen=True)
class OpDef:
    func: Callable
    arity: int | tuple[int, ...]
    kind: str
    doc: str = ""


OPS: dict[str, OpDef] = {}


def register(name: str, arity: int | tuple[int, ...], kind: str = "elementwise",
             doc: str = ""):
    def deco(func: Callable) -> Callable:
        OPS[name] = OpDef(func, arity, kind, doc)
        return func

    return deco


# --------------------------------------------------------------------------
# context & helpers
# --------------------------------------------------------------------------
@dataclass
class EvalContext:
    shape: tuple[int, int]
    mask: np.ndarray | None = None
    dtype: np.dtype = np.float32
    industry: np.ndarray | None = None

    @property
    def T(self) -> int:
        return self.shape[0]

    @property
    def N(self) -> int:
        return self.shape[1]

    def full(self, value: float = np.nan) -> np.ndarray:
        return np.full(self.shape, value, dtype=self.dtype)

    def as_array(self, x: Any) -> np.ndarray | float:
        if isinstance(x, np.ndarray):
            return x
        return float(x)

    def cs(self, a: np.ndarray) -> np.ndarray:
        """Apply the universe mask for cross-sectional operators."""
        if self.mask is None:
            return a
        return np.where(self.mask, a, np.nan)


def _float32(a: Any) -> np.ndarray | float:
    if isinstance(a, np.ndarray):
        return a.astype(np.float32, copy=False)
    return float(a)


def _clean(out: Any, ctx: EvalContext) -> np.ndarray | float:
    if not isinstance(out, np.ndarray):
        return float(out)
    if out.ndim == 0:
        return float(out)
    if out.ndim == 2 and out.shape != ctx.shape:
        if out.shape[1] == 1 and out.shape[0] == ctx.T:
            out = np.repeat(out, ctx.N, axis=1)
        else:
            out = np.broadcast_to(out, ctx.shape)
    return out.astype(ctx.dtype, copy=False)


def _binary(a: Any, b: Any, fn: Callable, ctx: EvalContext) -> np.ndarray | float:
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        out = fn(a, b)
    if isinstance(out, np.ndarray):
        if out.ndim == 0:
            return float(out) if math.isfinite(float(out)) else float("nan")
        out = np.where(np.isfinite(out), out, np.nan)
        return _clean(out, ctx)
    return float(out) if math.isfinite(float(out)) else float("nan")


def _rolling_sum(a: np.ndarray, w: int) -> np.ndarray:
    T, N = a.shape
    x = np.where(np.isfinite(a), a, 0.0).astype(np.float64)
    c = np.cumsum(x, axis=0)
    c = np.vstack([np.zeros((1, N)), c])
    out = np.full((T, N), np.nan, dtype=np.float64)
    out[w - 1:] = c[w:] - c[:-w]
    return out


def _rolling_count(a: np.ndarray, w: int) -> np.ndarray:
    T, N = a.shape
    x = np.isfinite(a).astype(np.float64)
    c = np.cumsum(x, axis=0)
    c = np.vstack([np.zeros((1, N)), c])
    out = np.full((T, N), np.nan, dtype=np.float64)
    out[w - 1:] = c[w:] - c[:-w]
    return out


def _window(a: np.ndarray, w: int) -> np.ndarray | None:
    if a.shape[0] < w:
        return None
    return np.lib.stride_tricks.sliding_window_view(a, w, axis=0)


def _chunked(a: np.ndarray, fn: Callable[[np.ndarray], np.ndarray],
             chunk: int = 160) -> np.ndarray:
    T, N = a.shape
    out = np.full((T, N), np.nan, dtype=np.float32)
    for c0 in range(0, N, chunk):
        out[:, c0:c0 + chunk] = fn(a[:, c0:c0 + chunk])
    return out


def _window_int(x: Any, name: str = "窗口") -> int:
    # WorldQuant uses floor(d) for non-integer window sizes
    w = int(math.floor(float(x)))
    if w < 1 or w > 500:
        raise ValueError(f"{name}长度必须在 [1, 500]，收到 {x}")
    return w


def _min_periods(w: int, minp: int | None = None) -> int:
    if minp is not None:
        return max(1, int(minp))
    return max(1, int(math.ceil(w * 0.6)))


def _nanmean_safe(a: np.ndarray, axis: int = -1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=axis)


# --------------------------------------------------------------------------
# elementwise
# --------------------------------------------------------------------------
@register("add", 2)
def _add(ctx, a, b): return _binary(a, b, np.add, ctx)


@register("sub", 2)
def _sub(ctx, a, b): return _binary(a, b, np.subtract, ctx)


@register("mul", 2)
def _mul(ctx, a, b): return _binary(a, b, np.multiply, ctx)


@register("div", 2)
def _div(ctx, a, b): return _binary(a, b, np.divide, ctx)


@register("pow", 2)
def _pow(ctx, a, b): return _binary(a, b, np.power, ctx)


@register("signed_power", 2, "elementwise", "sign(x)·|x|^a")
def _signed_power(ctx, a, b):
    a = np.asarray(a, dtype=np.float32)
    with np.errstate(all="ignore"):
        out = np.sign(a) * np.power(np.abs(a), np.asarray(b, dtype=np.float32))
    return _clean(np.where(np.isfinite(out), out, np.nan), ctx)


@register("signedpower", 2, "elementwise", "同 signed_power")
def _signedpower(ctx, a, b): return _signed_power(ctx, a, b)


@register("neg", 1)
def _neg(ctx, a):
    return _binary(a, -1.0, np.multiply, ctx)


@register("abs", 1)
def _abs(ctx, a): return _clean(np.abs(a), ctx)


@register("sign", 1)
def _sign(ctx, a): return _clean(np.sign(a), ctx)


@register("log", 1)
def _log(ctx, a):
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.asarray(a) > 0, np.log(np.maximum(a, 1e-12)), np.nan)
    return _clean(out, ctx)


@register("log1p", 1)
def _log1p(ctx, a):
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.asarray(a) > -1, np.log1p(np.maximum(a, -1 + 1e-12)), np.nan)
    return _clean(out, ctx)


@register("exp", 1)
def _exp(ctx, a): return _clean(np.exp(np.clip(a, -50, 50)), ctx)


@register("sqrt", 1)
def _sqrt(ctx, a):
    out = np.where(np.asarray(a) >= 0, np.sqrt(np.maximum(a, 0)), np.nan)
    return _clean(out, ctx)


@register("signed_log", 1)
def _signed_log(ctx, a):
    a = np.asarray(a)
    return _clean(np.sign(a) * np.log1p(np.abs(a)), ctx)


@register("clip", 3)
def _clip(ctx, a, lo, hi):
    return _clean(np.clip(a, lo, hi), ctx)


@register("min", 2)
def _min(ctx, a, b): return _binary(a, b, np.fmin, ctx)


@register("max", 2)
def _max(ctx, a, b): return _binary(a, b, np.fmax, ctx)


@register("gt", 2)
def _gt(ctx, a, b): return _clean((np.asarray(a) > np.asarray(b)).astype(np.float32), ctx)


@register("lt", 2)
def _lt(ctx, a, b): return _clean((np.asarray(a) < np.asarray(b)).astype(np.float32), ctx)


@register("ge", 2)
def _ge(ctx, a, b): return _clean((np.asarray(a) >= np.asarray(b)).astype(np.float32), ctx)


@register("le", 2)
def _le(ctx, a, b): return _clean((np.asarray(a) <= np.asarray(b)).astype(np.float32), ctx)


@register("eq", 2)
def _eq(ctx, a, b): return _clean((np.asarray(a) == np.asarray(b)).astype(np.float32), ctx)


@register("ne", 2)
def _ne(ctx, a, b): return _clean((np.asarray(a) != np.asarray(b)).astype(np.float32), ctx)


@register("and", 2)
def _and(ctx, a, b):
    return _clean(((np.asarray(a) > 0) & (np.asarray(b) > 0)).astype(np.float32), ctx)


@register("or", 2)
def _or(ctx, a, b):
    return _clean(((np.asarray(a) > 0) | (np.asarray(b) > 0)).astype(np.float32), ctx)


@register("not", 1)
def _not(ctx, a):
    return _clean((~(np.asarray(a) > 0)).astype(np.float32), ctx)


@register("isnan", 1)
def _isnan(ctx, a): return _clean(np.isnan(np.asarray(a)).astype(np.float32), ctx)


@register("isfinite", 1)
def _isfinite(ctx, a): return _clean(np.isfinite(np.asarray(a)).astype(np.float32), ctx)


@register("where", 3, "control")
def _where(ctx, cond, x, y):
    cond = np.asarray(cond)
    cond = np.where(np.isfinite(cond), cond > 0, False)
    with np.errstate(all="ignore"):
        out = np.where(cond, x, y)
    return _clean(out, ctx)


@register("neg_if", 2, "control")
def _neg_if(ctx, cond, x):
    cond = np.asarray(cond) > 0
    return _clean(np.where(cond, -np.asarray(x), np.asarray(x)), ctx)


# --------------------------------------------------------------------------
# cross-sectional
# --------------------------------------------------------------------------
@register("cs_rank", 1, "cs", "截面百分位排名")
def _cs_rank(ctx, a):
    a = np.asarray(a, dtype=np.float64)
    a = ctx.cs(a)
    T, N = a.shape
    valid = np.isfinite(a)
    x = np.where(valid, a, np.inf)
    order = np.argsort(x, axis=1, kind="stable")
    ranks = np.empty((T, N), dtype=np.float64)
    np.put_along_axis(ranks, order, np.broadcast_to(np.arange(N, dtype=np.float64), (T, N)), axis=1)
    cnt = valid.sum(axis=1, keepdims=True)
    out = np.where(valid, (ranks + 0.5) / np.maximum(cnt, 1), np.nan)
    return _clean(out, ctx)


@register("rank", 1, "cs", "同 cs_rank")
def _rank(ctx, a): return _cs_rank(ctx, a)


@register("cs_zscore", 1, "cs", "截面标准化")
def _cs_zscore(ctx, a):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(a, axis=1, keepdims=True)
        sd = np.nanstd(a, axis=1, keepdims=True)
    out = (a - mu) / np.where(sd > 1e-12, sd, np.nan)
    return _clean(out, ctx)


@register("zscore", 1, "cs")
def _zscore(ctx, a): return _cs_zscore(ctx, a)


@register("cs_demean", 1, "cs")
def _cs_demean(ctx, a):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(a, axis=1, keepdims=True)
    return _clean(a - mu, ctx)


@register("cs_indneutralize", 1, "cs", "行业内截面去均值")
def _cs_indneutralize(ctx, a):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    if ctx.industry is None:
        return _cs_demean(ctx, a)
    ind = np.asarray(ctx.industry, dtype=np.int64)
    K = int(ind.max()) + 1 if len(ind) else 0
    out = np.full_like(a, np.nan)
    for t in range(a.shape[0]):
        row = a[t]
        valid = np.isfinite(row)
        if valid.sum() < 2:
            continue
        idx = ind[valid]
        y = row[valid]
        cnt = np.bincount(idx, minlength=K).astype(np.float64)
        sums = np.bincount(idx, weights=y, minlength=K)
        out[t, valid] = y - (sums / np.maximum(cnt, 1))[idx]
    return _clean(out, ctx)


@register("cs_scale", 1, "cs")
def _cs_scale(ctx, a):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        denom = np.nansum(np.abs(a), axis=1, keepdims=True)
    return _clean(a / np.where(denom > 1e-12, denom, np.nan), ctx)


@register("cs_winsorize", 2, "cs", "MAD 去极值")
def _cs_winsorize(ctx, a, k):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(a, axis=1, keepdims=True)
        mad = np.nanmedian(np.abs(a - med), axis=1, keepdims=True)
    k = float(k)
    upper = med + k * 1.4826 * mad
    lower = med - k * 1.4826 * mad
    return _clean(np.clip(a, lower, upper), ctx)


@register("cs_quantile", 2, "cs", "截面分位数阈值")
def _cs_quantile(ctx, a, q):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    q = float(q)
    if not 0 <= q <= 1:
        raise ValueError("cs_quantile 的 q 必须在 [0,1]")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out = np.nanquantile(a, q, axis=1, keepdims=True)
    return _clean(out, ctx)


@register("cs_corr", 2, "cs")
def _cs_corr(ctx, a, b):
    a = ctx.cs(np.asarray(a, dtype=np.float64))
    b = ctx.cs(np.asarray(b, dtype=np.float64))
    valid = np.isfinite(a) & np.isfinite(b)
    a = np.where(valid, a, 0.0)
    b = np.where(valid, b, 0.0)
    cnt = valid.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        sa, sb = a.sum(1), b.sum(1)
        saa, sbb, sab = (a * a).sum(1), (b * b).sum(1), (a * b).sum(1)
        cov = sab - sa * sb / cnt
        va = saa - sa * sa / cnt
        vb = sbb - sb * sb / cnt
        corr = cov / np.sqrt(np.maximum(va * vb, 1e-24))
    out = np.where(cnt >= 3, corr, np.nan)
    return _clean(out.reshape(-1, 1), ctx)


# --------------------------------------------------------------------------
# time series
# --------------------------------------------------------------------------
@register("delay", 2, "ts", "滞后 n 期")
def _delay(ctx, a, n):
    a = np.asarray(a, dtype=np.float32)
    n = int(round(float(n)))
    out = np.full_like(a, np.nan)
    if 0 < n < a.shape[0]:
        out[n:] = a[:-n]
    elif n == 0:
        out = a.copy()
    return _clean(out, ctx)


@register("ref", 2, "ts")
def _ref(ctx, a, n): return _delay(ctx, a, n)


@register("delta", 2, "ts")
def _delta(ctx, a, n):
    a = np.asarray(a, dtype=np.float32)
    return _clean(a - _delay(ctx, a, n), ctx)


@register("pct_change", 2, "ts")
def _pct_change(ctx, a, n):
    a = np.asarray(a, dtype=np.float32)
    prev = _delay(ctx, a, n)
    return _binary(a, prev, lambda x, y: x / y - 1.0, ctx)


@register("ts_mean", 2, "ts", "滚动均值")
def _ts_mean(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    s = _rolling_sum(a, w)
    c = _rolling_count(a, w)
    out = s / np.where(c >= _min_periods(w), c, np.nan)
    return _clean(out, ctx)


@register("ts_sum", 2, "ts")
def _ts_sum(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    out = _rolling_sum(a, w)
    c = _rolling_count(a, w)
    out = np.where(c >= _min_periods(w), out, np.nan)
    return _clean(out, ctx)


@register("ts_std", 2, "ts", "滚动标准差")
def _ts_std(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    c = _rolling_count(a, w)
    s = _rolling_sum(a, w)
    s2 = _rolling_sum(a * a, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (s2 - s * s / c) / np.maximum(c - 1, 1)
    out = np.where(c >= _min_periods(w), np.sqrt(np.maximum(var, 0)), np.nan)
    return _clean(out, ctx)


@register("ts_var", 2, "ts")
def _ts_var(ctx, a, w):
    std = _ts_std(ctx, a, w)
    return _clean(np.asarray(std) ** 2, ctx)


@register("ts_min", 2, "ts")
def _ts_min(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    sw = _window(a, w)
    if sw is None:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = np.nanmin(view, axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_max", 2, "ts")
def _ts_max(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = np.nanmax(view, axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_rank", 2, "ts", "滚动分位排名")
def _ts_rank(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        last = block[w - 1:][:, :, None]
        valid = np.isfinite(view)
        lt = ((view < last) & valid).sum(-1)
        eq = ((view == last) & valid).sum(-1)
        cnt = valid.sum(-1)
        res = (lt + 0.5 * eq + 0.5) / np.maximum(cnt, 1)
        res = np.where(cnt >= _min_periods(w), res, np.nan)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_argmax", 2, "ts")
def _ts_argmax(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        valid = np.isfinite(view)
        idx = np.argmax(np.where(valid, view, -np.inf), axis=-1).astype(np.float32)
        res = np.where(valid.any(-1), idx, np.nan)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_argmin", 2, "ts")
def _ts_argmin(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        valid = np.isfinite(view)
        idx = np.argmin(np.where(valid, view, np.inf), axis=-1).astype(np.float32)
        res = np.where(valid.any(-1), idx, np.nan)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_corr", 3, "ts", "滚动相关系数")
def _ts_corr(ctx, a, b, w):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    w = _window_int(w)
    valid = np.isfinite(a) & np.isfinite(b)
    xa = np.where(valid, a, 0.0)
    xb = np.where(valid, b, 0.0)
    c = _rolling_count(np.where(valid, 1.0, np.nan), w)
    sa, sb = _rolling_sum(xa, w), _rolling_sum(xb, w)
    saa = _rolling_sum(xa * xa, w)
    sbb = _rolling_sum(xb * xb, w)
    sab = _rolling_sum(xa * xb, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sab - sa * sb / c
        va = saa - sa * sa / c
        vb = sbb - sb * sb / c
        corr = cov / np.sqrt(np.maximum(va * vb, 1e-24))
    out = np.where(c >= _min_periods(w), np.clip(corr, -1, 1), np.nan)
    return _clean(out, ctx)


@register("ts_cov", 3, "ts")
def _ts_cov(ctx, a, b, w):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    w = _window_int(w)
    valid = np.isfinite(a) & np.isfinite(b)
    xa, xb = np.where(valid, a, 0.0), np.where(valid, b, 0.0)
    c = _rolling_count(np.where(valid, 1.0, np.nan), w)
    cov = _rolling_sum(xa * xb, w) - _rolling_sum(xa, w) * _rolling_sum(xb, w) / c
    out = np.where(c >= _min_periods(w), cov / np.maximum(c - 1, 1), np.nan)
    return _clean(out, ctx)


@register("ts_quantile", 3, "ts")
def _ts_quantile(ctx, a, w, q):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    q = float(q)
    if not 0 <= q <= 1:
        raise ValueError("ts_quantile 的 q 必须在 [0,1]")
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = np.nanquantile(view, q, axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_decay_linear", 2, "ts", "线性衰减加权均值")
def _ts_decay_linear(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    weights = np.arange(1, w + 1, dtype=np.float64)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0).astype(np.float64)
        valid = np.isfinite(view)
        num = np.nansum(view * weights, axis=-1)
        den = (valid * weights).sum(-1)
        res = num / np.where(den > 0, den, np.nan)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_ema", 2, "ts", "指数移动平均")
def _ts_ema(ctx, a, span):
    a = np.asarray(a, dtype=np.float32)
    span = _window_int(span)
    alpha = 2.0 / (span + 1.0)
    T, N = a.shape
    out = np.full((T, N), np.nan, dtype=np.float64)
    prev = np.full(N, np.nan, dtype=np.float64)
    for t in range(T):
        x = a[t].astype(np.float64)
        valid = np.isfinite(x)
        new = np.where(np.isfinite(prev), alpha * x + (1 - alpha) * prev, x)
        prev = np.where(valid, new, prev)
        out[t] = prev
    return _clean(out, ctx)


@register("ts_ir", 2, "ts", "信息比率 mean/std")
def _ts_ir(ctx, a, w):
    mean = np.asarray(_ts_mean(ctx, a, w), dtype=np.float64)
    std = np.asarray(_ts_std(ctx, a, w), dtype=np.float64)
    return _clean(mean / np.where(std > 1e-12, std, np.nan), ctx)


@register("ts_zscore", 2, "ts")
def _ts_zscore(ctx, a, w):
    mean = np.asarray(_ts_mean(ctx, a, w), dtype=np.float64)
    std = np.asarray(_ts_std(ctx, a, w), dtype=np.float64)
    return _clean((np.asarray(a, dtype=np.float64) - mean) / np.where(std > 1e-12, std, np.nan), ctx)


@register("ts_skew", 2, "ts")
def _ts_skew(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(view, axis=-1, keepdims=True)
            dev = view - mu
            m2 = np.nanmean(dev ** 2, axis=-1)
            m3 = np.nanmean(dev ** 3, axis=-1)
            res = m3 / np.maximum(m2, 1e-24) ** 1.5
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_kurt", 2, "ts")
def _ts_kurt(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(view, axis=-1, keepdims=True)
            dev = view - mu
            m2 = np.nanmean(dev ** 2, axis=-1)
            m4 = np.nanmean(dev ** 4, axis=-1)
            res = m4 / np.maximum(m2, 1e-24) ** 2 - 3.0
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_maxdiff", 2, "ts")
def _ts_maxdiff(ctx, a, w):
    return _clean(np.asarray(a, dtype=np.float32) - np.asarray(_ts_max(ctx, a, w)), ctx)


@register("ts_mindiff", 2, "ts")
def _ts_mindiff(ctx, a, w):
    return _clean(np.asarray(a, dtype=np.float32) - np.asarray(_ts_min(ctx, a, w)), ctx)


@register("ts_wma", 2, "ts")
def _ts_wma(ctx, a, w): return _ts_decay_linear(ctx, a, w)


# --------------------------------------------------------------------------
# introspection
# --------------------------------------------------------------------------
def list_ops(kind: str | None = None) -> dict[str, OpDef]:
    if kind is None:
        return dict(OPS)
    return {k: v for k, v in OPS.items() if v.kind == kind}


def op_help() -> list[dict]:
    return [{"name": k, "arity": v.arity, "kind": v.kind, "doc": v.doc}
            for k, v in sorted(OPS.items())]


# --------------------------------------------------------------------------
# Alpha158 compatibility operators
# --------------------------------------------------------------------------
@register("ts_median", 2, "ts", "滚动中位数")
def _ts_median(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = np.nanmedian(view, axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_mad", 2, "ts", "滚动 MAD")
def _ts_mad(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(view, axis=-1, keepdims=True)
            res = np.nanmedian(np.abs(view - med), axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_product", 2, "ts", "滚动乘积")
def _ts_product(ctx, a, w):
    a = np.asarray(a, dtype=np.float64)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            res = np.nanprod(view, axis=-1)
        out = np.full((block.shape[0], block.shape[1]), np.nan, dtype=np.float32)
        out[w - 1:] = res
        return out
    return _clean(_chunked(a, fn), ctx)


@register("ts_count", 2, "ts", "滚动有效样本数")
def _ts_count(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    out = _rolling_count(a, w)
    out = np.where(out > 0, out, np.nan)
    return _clean(out, ctx)


def _linreg_blocks(block: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    T, N = block.shape
    view = np.lib.stride_tricks.sliding_window_view(block, w, axis=0).astype(np.float64)
    t = np.arange(w, dtype=np.float64)
    valid = np.isfinite(view)
    x = np.where(valid, t, 0.0)
    y = np.where(valid, view, 0.0)
    n = valid.sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        xbar = x.sum(-1) / n
        ybar = y.sum(-1) / n
        dx = x - xbar[..., None]
        dy = y - ybar[..., None]
        sxx = (dx * dx).sum(-1)
        sxy = (dx * dy).sum(-1)
        slope = sxy / np.where(sxx > 1e-12, sxx, np.nan)
        intercept = ybar - slope * xbar
        pred = intercept[..., None] + slope[..., None] * t
        resid = y - pred
        sse = (resid ** 2).sum(-1)
        sst = (dy ** 2).sum(-1)
        rsq = 1.0 - sse / np.where(sst > 1e-12, sst, np.nan)
        last_resid = resid[..., -1]
    out = np.full((T, N), np.nan, dtype=np.float32)
    return out, (slope, rsq, last_resid, n)


def _place(out: np.ndarray, values: np.ndarray, valid: np.ndarray, w: int) -> np.ndarray:
    res = values.copy()
    res[~valid] = np.nan
    out[w - 1:] = res
    return out


@register("ts_slope", 2, "ts", "滚动线性回归斜率")
def _ts_slope(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        out, (slope, rsq, resid, n) = _linreg_blocks(block, w)
        return _place(out, slope, n >= _min_periods(w), w)
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_rsquare", 2, "ts", "滚动线性回归 R²")
def _ts_rsquare(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        out, (slope, rsq, resid, n) = _linreg_blocks(block, w)
        return _place(out, rsq, n >= _min_periods(w), w)
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_resi", 2, "ts", "滚动线性回归末端残差")
def _ts_resi(ctx, a, w):
    a = np.asarray(a, dtype=np.float32)
    w = _window_int(w)
    if a.shape[0] < w:
        return _clean(ctx.full(), ctx)
    def fn(block):
        out, (slope, rsq, resid, n) = _linreg_blocks(block, w)
        return _place(out, resid, n >= _min_periods(w), w)
    return _clean(_chunked(a, fn, chunk=96), ctx)


@register("ts_idxmax", 2, "ts")
def _ts_idxmax(ctx, a, w): return _ts_argmax(ctx, a, w)


@register("ts_idxmin", 2, "ts")
def _ts_idxmin(ctx, a, w): return _ts_argmin(ctx, a, w)
