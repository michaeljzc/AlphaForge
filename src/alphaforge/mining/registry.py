"""Factor registry (append-only JSONL with dedupe by expression hash)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.utils import read_json, write_json


class FactorRegistry:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.path = self.cfg.paths.factors / "registry.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _key(self, expression: str) -> str:
        return hashlib.sha1(expression.encode("utf-8")).hexdigest()[:16]

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def exists(self, expression: str) -> bool:
        key = self._key(expression)
        return any(r.get("key") == key for r in self.records())

    def add(self, name: str, expression: str, category: str = "mined",
            direction: int = 1, metrics: dict[str, Any] | None = None,
            source: str = "gp", notes: str = "") -> dict[str, Any]:
        key = self._key(expression)
        rec = {
            "key": key, "name": name, "expression": expression, "category": category,
            "direction": direction, "metrics": metrics or {}, "source": source,
            "notes": notes, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=float) + "\n")
        return rec

    def frame(self) -> pd.DataFrame:
        recs = self.records()
        if not recs:
            return pd.DataFrame(columns=["key", "name", "expression", "category",
                                         "direction", "source", "created_at"])
        rows = []
        for r in recs:
            flat = {k: v for k, v in r.items() if k != "metrics"}
            flat.update({f"metric_{k}": v for k, v in (r.get("metrics") or {}).items()})
            rows.append(flat)
        return pd.DataFrame(rows)

    def save_snapshot(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else self.cfg.paths.factors / "registry_snapshot.json"
        write_json(p, self.records())
        return p
