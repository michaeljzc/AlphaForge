from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _deep_update(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


@dataclass
class Paths:
    root: Path
    data: Path
    market_db: Path
    qlib_dir: Path
    cache: Path
    factors: Path
    reports: Path

    def ensure(self) -> None:
        for path in (self.data, self.data / "events", self.cache, self.factors, self.reports):
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    # -- attribute-style access to the nested yaml document -----------------
    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def paths(self) -> Paths:
        p = self.get("paths", {})
        return Paths(
            root=ROOT,
            data=ROOT / p.get("data", "data"),
            market_db=ROOT / p.get("market_db", "data/market.db"),
            qlib_dir=ROOT / p.get("qlib_dir", "data/qlib_cn"),
            cache=ROOT / p.get("cache", "data/cache"),
            factors=ROOT / p.get("factors", "artifacts/factors"),
            reports=ROOT / p.get("reports", "reports"),
        )

    @property
    def data_start(self) -> str:
        return self.get("data.start", "2019-01-01")

    @property
    def data_end(self) -> str:
        return self.get("data.end", "2026-10-31")

    @property
    def benchmark(self) -> str:
        return self.get("data.benchmark", "000300.SH")


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    """Load YAML config; ``path`` may be a file or a directory containing default.yaml."""
    if path is None:
        candidate = ROOT / "configs" / "default.yaml"
    else:
        p = Path(path)
        if p.is_dir():
            candidate = p / "default.yaml"
        else:
            candidate = p
    raw: dict[str, Any] = {}
    if candidate.exists():
        raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    if overrides:
        _deep_update(raw, overrides)
    cfg = Config(raw=raw, path=candidate)
    cfg.paths.ensure()
    return cfg


def resolve_token(cfg: Config) -> str:
    """Resolve Tushare token: env var -> configured files -> local credentials.json."""
    env_name = cfg.get("data.tushare_token_env", "TUSHARE_TOKEN")
    token = os.environ.get(env_name, "").strip()
    if token:
        return token
    candidates = list(cfg.get("data.tushare_token_files", []) or [])
    candidates.append(str(ROOT / "config" / "credentials.json"))
    for item in candidates:
        p = Path(item).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            continue
        try:
            import json

            doc = json.loads(p.read_text(encoding="utf-8"))
            token = str(doc.get("TUSHARE_TOKEN", "")).strip()
            if token:
                return token
        except Exception:
            continue
    raise RuntimeError(
        "未找到 Tushare token：请设置环境变量 TUSHARE_TOKEN，或在 config/credentials.json 写入 "
        '{"TUSHARE_TOKEN": "..."}'
    )
