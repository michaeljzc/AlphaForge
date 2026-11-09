"""Factor preprocessing: winsorize -> standardize -> neutralize.

The order follows the research report (and sell-side practice): 去极值 →
标准化 → 行业/市值中性化.  Neutralisation is a cross-sectional regression of
the factor on industry dummies and log market cap, implemented via Frisch-
Waugh-Lovell (industry demeaning first, then size residualisation).
"""

from __future__ import annotations

import warnings

import numpy as np

from alphaforge.config import Config
from alphaforge.data.panel import Panel


def winsorize_mad(arr: np.ndarray, k: float = 3.0,
                  mask: np.ndarray | None = None) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64).copy()
    if mask is not None:
        a = np.where(mask, a, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(a, axis=1, keepdims=True)
        mad = np.nanmedian(np.abs(a - med), axis=1, keepdims=True)
    upper = med + k * 1.4826 * mad
    lower = med - k * 1.4826 * mad
    out = np.clip(a, lower, upper)
    if mask is not None:
        out = np.where(mask, out, np.nan)
    return out


def zscore(arr: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64).copy()
    if mask is not None:
        a = np.where(mask, a, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(a, axis=1, keepdims=True)
        sd = np.nanstd(a, axis=1, keepdims=True)
    out = (a - mu) / np.where(sd > 1e-12, sd, np.nan)
    if mask is not None:
        out = np.where(mask, out, np.nan)
    return out


def neutralize(arr: np.ndarray, panel: Panel, mask: np.ndarray | None = None,
               industry: bool = True, size: bool = True,
               min_names: int = 20) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64).copy()
    if mask is not None:
        a = np.where(mask, a, np.nan)
    T, N = a.shape
    out = np.full((T, N), np.nan, dtype=np.float64)
    ind = panel.industry_id.astype(np.int64)
    K = int(ind.max()) + 1 if N else 0
    sz = panel.field("log_mv").astype(np.float64) if size else None

    for t in range(T):
        row = a[t]
        valid = np.isfinite(row)
        if size:
            valid &= np.isfinite(sz[t])
        if valid.sum() < min_names:
            continue
        y = row[valid]
        s = sz[t][valid] if size else None
        idx = ind[valid]
        if industry:
            cnt = np.bincount(idx, minlength=K).astype(np.float64)
            cy = np.bincount(idx, weights=y, minlength=K)
            y_res = y - (cy / np.maximum(cnt, 1))[idx]
            if size:
                cs = np.bincount(idx, weights=s, minlength=K)
                s_res = s - (cs / np.maximum(cnt, 1))[idx]
            else:
                s_res = None
        else:
            y_res = y - y.mean()
            s_res = (s - s.mean()) if size else None
        if size and s_res is not None:
            denom = float(np.sum(s_res * s_res))
            if denom > 1e-12:
                beta = float(np.sum(y_res * s_res)) / denom
                y_res = y_res - beta * s_res
        out[t, valid] = y_res
    return out


def preprocess(arr: np.ndarray, panel: Panel, cfg: Config | None = None,
               mask: np.ndarray | None = None) -> np.ndarray:
    """Full three-step pipeline.  ``mask`` is usually the universe mask."""
    if mask is None:
        mask = panel.mask("universe")
    cfg = cfg or Config()
    method = str(cfg.get("preprocess.winsorize", "mad")).lower()
    k = float(cfg.get("preprocess.mad_k", 3.0))
    neutralize_cfg = cfg.get("preprocess.neutralize", ["industry", "size"]) or []
    out = np.asarray(arr, dtype=np.float64)
    if method == "mad":
        out = winsorize_mad(out, k=k, mask=mask)
    elif method == "sigma":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mu = np.nanmean(np.where(mask, out, np.nan), axis=1, keepdims=True)
            sd = np.nanstd(np.where(mask, out, np.nan), axis=1, keepdims=True)
        out = np.clip(out, mu - k * sd, mu + k * sd)
        out = np.where(mask, out, np.nan)
    out = zscore(out, mask=mask)
    if neutralize_cfg:
        out = neutralize(
            out, panel, mask=mask,
            industry="industry" in neutralize_cfg,
            size=("size" in neutralize_cfg or "log_mv" in neutralize_cfg),
        )
    else:
        out = np.where(mask, out, np.nan)
    return out.astype(np.float32)


def coverage(arr: np.ndarray, mask: np.ndarray | None = None) -> float:
    valid = np.isfinite(arr)
    if mask is not None:
        return float(valid[mask].mean()) if mask.any() else 0.0
    return float(valid.mean())
