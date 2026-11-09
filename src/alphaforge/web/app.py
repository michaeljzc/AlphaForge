"""AlphaForge local web console (FastAPI + vanilla JS + ECharts).

Run with::

    alphaforge web --port 8787
    # http://127.0.0.1:8787

The server only reads local artefacts under ``reports/artifacts`` and the
market lake; it never uploads data.  It binds to 127.0.0.1 by default.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alphaforge.config import load_config
from alphaforge.utils import read_json

WEB_DIR = Path(__file__).resolve().parent
STATIC = WEB_DIR / "static"
CFG = load_config(os.environ.get("ALPHAFORGE_CONFIG") or None)
ART = CFG.paths.reports / "artifacts"
FACTORS_DIR = ART / "factors"

app = FastAPI(title="AlphaForge Console", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

_PANEL = None


def _panel():
    global _PANEL
    if _PANEL is None:
        from alphaforge.data.panel import load_panel

        _PANEL = load_panel(CFG)
    return _PANEL


def _read(path: Path, default: Any = None) -> Any:
    return read_json(path, default)


def _sanitize(value: Any) -> Any:
    """JSON has no NaN/Inf; FastAPI rejects them. Replace with null."""
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.ndarray):
        return _sanitize(value.tolist())
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _factors_index() -> list[dict[str, Any]]:
    doc = _read(FACTORS_DIR / "index.json", {"factors": []})
    if isinstance(doc, dict):
        return doc.get("factors", [])
    return doc or []


def _factor_file(name: str) -> Path | None:
    for item in _factors_index():
        if item.get("name") == name:
            f = FACTORS_DIR / str(item.get("file"))
            return f if f.exists() else None
    return None


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.2.0", "time": int(time.time())}


@app.get("/api/overview")
def overview():
    demo = _read(ART / "demo_summary.json", {}) or {}
    backtest = _read(ART / "backtest.json", {}) or {}
    events = _read(ART / "events.json", {}) or {}
    qlib = _read(ART / "qlib.json", {}) or {}
    native = _read(ART / "qlib_native.json", {}) or {}
    gp = _read(ART / "gp.json", {}) or _read(ART / "factors" / "gp_latest.json", {}) or {}
    factors = _factors_index()
    return _sanitize({
        "demo": demo,
        "panel": demo.get("panel", {}),
        "backtest_metrics": backtest.get("metrics", {}),
        "events": {"summary": events.get("summary", {}),
                   "audit": events.get("audit", {}),
                   "ic": (events.get("ic") or [])[:8]},
        "qlib": qlib,
        "qlib_native": {"ic": native.get("ic", {}),
                        "backtest": {k: v for k, v in (native.get("qlib_backtest") or {}).items()
                                     if k not in ("equity", "dates", "benchmark_equity", "traceback")}},
        "gp": {"history": gp.get("history", [])},
        "factors": factors[:12],
        "generated_at": demo.get("meta", {}).get("generated"),
        "artifacts": {
            "factors": len(factors),
            "has_backtest": (ART / "backtest.json").exists(),
            "has_events": (ART / "events.json").exists(),
            "has_native": (ART / "qlib_native.json").exists(),
        },
    })


@app.get("/api/backtest")
def backtest():
    doc = _read(ART / "backtest.json")
    if not doc:
        raise HTTPException(404, "backtest.json 不存在，请先运行 alphaforge demo")
    return _sanitize(doc)


@app.get("/api/events")
def events():
    doc = _read(ART / "events.json")
    if not doc:
        raise HTTPException(404, "events.json 不存在，请先运行 alphaforge demo")
    return _sanitize(doc)


@app.get("/api/gp")
def gp():
    doc = _read(ART / "gp.json") or _read(ART / "factors" / "gp_latest.json")
    if not doc:
        raise HTTPException(404, "GP 结果不存在，请运行 alphaforge factors mine")
    return _sanitize(doc)


@app.get("/api/qlib")
def qlib():
    return _sanitize({"data": _read(ART / "qlib.json", {}),
                      "native": _read(ART / "qlib_native.json", {})})


@app.get("/api/factors")
def factors(category: str | None = None):
    items = _factors_index()
    if category:
        items = [x for x in items if x.get("category") == category]
    return _sanitize({"factors": items, "count": len(items),
                      "categories": sorted({x.get("category") for x in items})})


@app.get("/api/library")
def library():
    from alphaforge.expr.library import FACTORS, alpha158_factors

    evaluated = {x.get("name"): x for x in _factors_index()}
    items = []
    for f in list(FACTORS.values()) + alpha158_factors():
        row = f.to_dict()
        e = evaluated.get(f.name)
        row["evaluated"] = bool(e)
        if e:
            for key in ("ic", "icir", "hit", "mono", "ls_ann", "net_ann",
                        "dir_net", "turnover", "coverage", "verdict", "file"):
                row[key] = e.get(key)
        items.append(row)
    return _sanitize({"factors": items, "count": len(items)})


@app.get("/api/factors/{name}")
def factor_detail(name: str):
    f = _factor_file(name)
    if not f:
        raise HTTPException(404, f"因子 {name} 的评估快照不存在")
    return _sanitize(_read(f))


class EvalRequest(BaseModel):
    expression: str
    name: str = ""
    description: str = ""
    start: str = "2021-01-01"
    end: str | None = None
    horizon: int = 5
    preprocess: bool = True


@app.post("/api/factors/evaluate")
def evaluate_factor_api(req: EvalRequest):
    from alphaforge.evaluate.core import evaluate_factor
    from alphaforge.report.artifacts import factor_payload

    try:
        panel = _panel()
        rep = evaluate_factor(panel, req.expression, name=req.name or req.expression[:48],
                              cfg=CFG, start=req.start, end=req.end,
                              horizons=sorted({1, 5, 20, 60, req.horizon}),
                              do_preprocess=req.preprocess,
                              description=req.description)
        payload = factor_payload(rep)
        payload["ad_hoc"] = True
        return _sanitize({"ok": True, "factor": payload})
    except Exception as exc:
        return JSONResponse(status_code=400,
                            content={"ok": False, "error": str(exc)[:500]})


@app.get("/api/data/summary")
def data_summary():
    from alphaforge.data.schema import TABLES
    from alphaforge.utils import connect

    counts = {}
    try:
        conn = connect(CFG.paths.market_db, readonly=True)
        for table in TABLES:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                counts[table] = None
        conn.close()
    except Exception as exc:
        return {"error": str(exc)[:200], "counts": counts}
    demo = _read(ART / "demo_summary.json", {}) or {}
    return _sanitize({"counts": counts, "panel": demo.get("panel", {}),
                      "db": str(CFG.paths.market_db), "qlib_dir": str(CFG.paths.qlib_dir)})


@app.get("/api/sources")
def sources(probe: bool = False):
    from alphaforge.data.sources import status

    rows = status(probe=probe)
    return _sanitize({"sources": rows})


@app.post("/api/sources/{source}/probe")
def source_probe(source: str):
    from alphaforge.data.sources import probe_source

    if source not in ("tushare", "ifind", "datayes"):
        raise HTTPException(400, "未知数据源")
    return _sanitize({"source": source, **probe_source(source, use_cache=False)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
