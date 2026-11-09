"""Export the panel to Qlib's binary data format.

Layout::

    qlib_cn/
      calendars/day.txt
      instruments/all.txt
      features/SH600000/close.day.bin
      ...

The panel already stores forward-adjusted prices, so ``$factor`` is exported
as 1.0.  This keeps ``D.features(['SH600000'], ['$close'])`` numerically equal
to AlphaForge's ``close`` field, which is what the parity test asserts.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel, load_panel
from alphaforge.utils import Timer, dashed, write_json

QLIB_FIELDS = ["open", "high", "low", "close", "vwap", "volume", "amount"]


def qlib_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith("92"):
        return "BJ" + code
    if code.startswith(("6", "9")):
        return "SH" + code
    if code.startswith(("0", "2", "3")):
        return "SZ" + code
    if code.startswith(("4", "8")):
        return "BJ" + code
    return "SH" + code


def _write_bin(path: Path, values: np.ndarray, start_idx: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.empty(len(values) + 1, dtype="<f4")
    arr[0] = float(start_idx)
    arr[1:] = values.astype(np.float32)
    arr.tofile(path)


class QlibExporter:
    def __init__(self, cfg: Config, panel: Panel):
        self.cfg = cfg
        self.panel = panel
        self.root = cfg.paths.qlib_dir

    def export(self, force: bool = False, fields: list[str] | None = None) -> dict:
        fields = fields or QLIB_FIELDS
        root = self.root
        marker = root / ".alphaforge_export.json"
        if marker.exists() and not force:
            meta = json.loads(marker.read_text())
            if meta.get("signature") == self._signature():
                print(f"[qlib] export up-to-date ({meta.get('symbols')} symbols)")
                return meta

        if force and root.exists():
            shutil.rmtree(root)
        (root / "calendars").mkdir(parents=True, exist_ok=True)
        (root / "instruments").mkdir(parents=True, exist_ok=True)
        (root / "features").mkdir(parents=True, exist_ok=True)

        dates = self.panel.date_strs
        (root / "calendars" / "day.txt").write_text("\n".join(dates) + "\n", encoding="utf-8")

        T = len(dates)
        close = self.panel.field("close")
        lines = []
        with Timer("qlib export"):
            for j, code in enumerate(self.panel.symbols):
                sym = qlib_symbol(code)
                valid = np.isfinite(close[:, j])
                if not valid.any():
                    continue
                first = int(np.argmax(valid))
                last = int(T - 1 - np.argmax(valid[::-1]))
                lines.append(f"{sym}\t{dates[first]}\t{dates[last]}")
                for f in fields:
                    self._write_field(sym, f, self.panel.data[f][:, j], first)
                self._write_field(sym, "factor",
                                  np.ones(T, dtype=np.float32), first)

        bench_lines = self._export_benchmarks(dates)
        (root / "instruments" / "all.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # convenience universe files
        (root / "instruments" / "alphaforge.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        (root / "instruments" / "benchmark.txt").write_text(
            "\n".join(bench_lines) + "\n", encoding="utf-8")
        meta = {
            "symbols": len(lines),
            "dates": T,
            "start": dates[0],
            "end": dates[-1],
            "fields": fields + ["factor"],
            "benchmarks": [line.split("\t")[0] for line in bench_lines],
            "signature": self._signature(),
        }
        write_json(marker, meta)
        print(f"[qlib] exported {len(lines)} symbols -> {root}")
        return meta

    def _export_benchmarks(self, dates: list[str]) -> list[str]:
        """Export index_daily close/volume as Qlib instruments (SH000300 ...)."""
        from alphaforge.utils import connect

        mapping = {"000300": "SH000300", "000905": "SH000905", "000852": "SH000852"}
        out: list[str] = []
        try:
            conn = connect(self.cfg.paths.market_db, readonly=True)
            for code, sym in mapping.items():
                df = pd.read_sql_query(
                    "SELECT date,open,high,low,close,volume,amount FROM index_daily "
                    "WHERE code=? ORDER BY date", conn, params=[code])
                if df.empty:
                    continue
                s = df.set_index("date").reindex(dates).ffill()
                valid = s["close"].notna().to_numpy()
                if not valid.any():
                    continue
                first = int(np.argmax(valid))
                last = int(len(valid) - 1 - np.argmax(valid[::-1]))
                out.append(f"{sym}\t{dates[first]}\t{dates[last]}")
                for f in QLIB_FIELDS:
                    if f == "vwap":
                        v = (s["amount"] / s["volume"].replace(0, np.nan)).to_numpy()
                    else:
                        v = s[f].to_numpy() if f in s else np.full(len(dates), np.nan)
                    self._write_field(sym, f, v.astype(np.float32), first)
                self._write_field(sym, "factor", np.ones(len(dates), dtype=np.float32), first)
            conn.close()
        except Exception as exc:
            print(f"[qlib] benchmark export skipped: {exc}")
        return out

    def _write_field(self, sym: str, field: str, values: np.ndarray, start_idx: int) -> None:
        _write_bin(self.root / "features" / sym / f"{field.lower()}.day.bin", values, start_idx)

    def _signature(self) -> str:
        return f"{self.panel.shape}-{self.panel.dates[0]}-{self.panel.dates[-1]}-bench"


def export_qlib(cfg: Config | None = None, force: bool = False) -> dict:
    cfg = cfg or load_config()
    panel = load_panel(cfg)
    return QlibExporter(cfg, panel).export(force=force)


def qlib_init(cfg: Config | None = None):
    """Initialise Qlib against the exported data directory (idempotent)."""
    import qlib
    from qlib.constant import REG_CN

    cfg = cfg or load_config()
    uri = str(cfg.paths.qlib_dir)
    if not (cfg.paths.qlib_dir / "calendars" / "day.txt").exists():
        raise RuntimeError("Qlib 数据目录尚未导出，请先运行 `alphaforge build-panel --export-qlib`")
    qlib.init(provider_uri=uri, region=REG_CN, expression_cache=None, dataset_cache=None,
              logging_level="ERROR")
    return uri


def verify_parity(cfg: Config | None = None, n: int = 3) -> dict:
    """Compare AlphaForge panel fields with Qlib ``D.features`` output."""
    cfg = cfg or load_config()
    qlib_init(cfg)
    from qlib.data import D

    panel = load_panel(cfg)
    codes = panel.symbols[:n]
    start, end = panel.date_strs[0], panel.date_strs[-1]
    result = {"checked": [], "max_abs_diff": 0.0}
    for code in codes:
        sym = qlib_symbol(code)
        df = D.features([sym], ["$close", "$open", "$volume"],
                        start_time=start, end_time=end)
        if df.empty:
            continue
        df.index = df.index.get_level_values("datetime").strftime("%Y-%m-%d")
        j = panel.symbol_index(code)
        for field, col in [("close", "$close"), ("open", "$open"), ("volume", "$volume")]:
            ours = panel.data[field][:, j]
            theirs = df[col].to_numpy(dtype=np.float64)
            mask = np.isfinite(ours) & np.isfinite(theirs)
            if mask.sum() == 0:
                continue
            diff = float(np.max(np.abs(ours[mask] - theirs[mask])))
            result["checked"].append({"code": code, "field": field, "points": int(mask.sum()),
                                      "max_abs_diff": diff})
            result["max_abs_diff"] = max(result["max_abs_diff"], diff)
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Export panel to Qlib binary format")
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.verify:
        print(json.dumps(verify_parity(cfg), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(export_qlib(cfg, force=args.force), ensure_ascii=False, indent=2))
