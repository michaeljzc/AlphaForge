"""Serialise factor evaluation reports for the web console."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from alphaforge.evaluate.core import FactorReport
from alphaforge.utils import read_json, write_json


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", name)[:80] or "factor"


def _series_payload(s: pd.Series | None) -> dict[str, list]:
    if s is None or len(s) == 0:
        return {"dates": [], "values": []}
    s = pd.Series(s)
    s.index = pd.to_datetime(s.index)
    return {"dates": [str(d.date()) for d in s.index],
            "values": [float(v) for v in s.to_numpy()]}


def factor_payload(report: FactorReport) -> dict[str, Any]:
    primary = report.primary_horizon
    ic_curves = {str(h): _series_payload(s) for h, s in report.ic_series.items()}
    curves = {"q": {"dates": [], "series": {}},
              "ls": {"dates": [], "values": []}}
    if report.q_curves is not None and not report.q_curves.empty:
        q = report.q_curves.copy()
        q.index = pd.to_datetime(q.index)
        curves["q"]["dates"] = [str(d.date()) for d in q.index]
        curves["q"]["series"] = {c: [float(v) for v in q[c].to_numpy()] for c in q.columns}
    if report.ls_curve is not None and len(report.ls_curve):
        ls = pd.Series(report.ls_curve)
        ls.index = pd.to_datetime(ls.index)
        curves["ls"]["dates"] = [str(d.date()) for d in ls.index]
        curves["ls"]["values"] = [float(v) for v in ls.to_numpy()]
    qmean = {}
    if report.qret is not None and not report.qret.empty:
        qmean = {c: float(v) for c, v in report.qret.mean().items()}
    return {
        "name": report.name,
        "expression": report.expression,
        "category": report.category,
        "description": report.description,
        "direction": report.direction,
        "verdict": report.verdict,
        "period": report.period,
        "coverage": float(report.coverage),
        "primary_horizon": primary,
        "ic": {str(k): v for k, v in report.ic.items()},
        "quantile_mean": qmean,
        "quantile": {k: v for k, v in report.quantile.items() if k != "curves"},
        "turnover": {k: v for k, v in report.turnover.items() if k != "series"},
        "autocorr": float(report.autocorr),
        "neutralized": report.neutralized,
        "gate": report.gate,
        "curves": curves,
        "ic_curves": ic_curves,
    }


def enrich_factor_descriptions(cfg) -> dict[str, Any]:
    """Backfill Chinese descriptions into existing factor snapshots/index."""
    from alphaforge.expr.library import FACTORS, alpha158_description

    directory = cfg.paths.reports / "artifacts" / "factors"
    index_path = directory / "index.json"
    doc = read_json(index_path, {}) or {}
    items = doc.get("factors", [])
    updated = 0
    for item in items:
        name = item.get("name", "")
        desc = ""
        if name in FACTORS:
            desc = FACTORS[name].description
        elif name.startswith("a158_"):
            desc = alpha158_description(name)
        if not desc:
            continue
        item["description"] = desc
        fpath = directory / str(item.get("file", ""))
        if fpath.exists():
            payload = read_json(fpath, {}) or {}
            if payload.get("description") != desc:
                payload["description"] = desc
                write_json(fpath, payload)
                updated += 1
    if items:
        write_json(index_path, {"factors": items})
    # demo summary leaderboard (used by the report)
    summary_path = cfg.paths.reports / "artifacts" / "demo_summary.json"
    summary = read_json(summary_path)
    if isinstance(summary, dict) and summary.get("leaderboard"):
        for row in summary["leaderboard"]:
            if row.get("name") in FACTORS:
                row["description"] = FACTORS[row["name"]].description
        write_json(summary_path, summary)
    return {"n": len(items), "updated": updated}


def save_factor_artifacts(reports: list[FactorReport], directory: str | Path,
                          merge: bool = False) -> dict[str, Any]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    if merge and (directory / "index.json").exists():
        old = (read_json(directory / "index.json", {}) or {}).get("factors", [])
        index.extend(old)
    for report in reports:
        payload = factor_payload(report)
        write_json(directory / f"{_safe(report.name)}.json", payload)
        p = report.ic.get(report.primary_horizon, {})
        q = report.quantile.get("long_short", {})
        index.append({
            "name": report.name,
            "expression": report.expression,
            "category": report.category,
            "description": report.description,
            "verdict": report.verdict,
            "ic": p.get("mean_monthly", p.get("mean")),
            "icir": p.get("icir_monthly", p.get("icir")),
            "hit": p.get("hit_rate_monthly", p.get("hit_rate")),
            "mono": report.quantile.get("monotonicity"),
            "ls_ann": q.get("annualized"),
            "net_ann": q.get("net_annualized"),
            "dir_net": q.get("directional_net_annualized"),
            "turnover": report.turnover.get("mean"),
            "coverage": report.coverage,
            "file": f"{_safe(report.name)}.json",
        })
    # dedupe by name, new snapshots win
    by_name = {r["name"]: r for r in index}
    index = list(by_name.values())
    index.sort(key=lambda r: abs(r.get("ic") or 0), reverse=True)
    write_json(directory / "index.json", {"factors": index})
    return {"n": len(index), "dir": str(directory), "factors": index}
