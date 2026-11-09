from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------
def compact(value: str | date | datetime) -> str:
    """Return YYYYMMDD."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y%m%d")
    s = str(value).strip().replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"非法日期: {value}")
    return s


def dashed(value: str | date | datetime) -> str:
    """Return YYYY-MM-DD."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if "-" in s:
        return s
    s = compact(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def shift_days(value: str, days: int) -> str:
    d = datetime.strptime(dashed(value), "%Y-%m-%d").date()
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# codes
# --------------------------------------------------------------------------
def to_code(ts_code: str) -> str:
    """600000.SH -> 600000"""
    return ts_code.split(".")[0]


def to_ts_code(code: str, exchange: str | None = None) -> str:
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        suffix = "SH"
    elif code.startswith(("0", "2", "3")):
        suffix = "SZ"
    elif code.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = exchange or "SH"
    return f"{code}.{suffix}"


def board_of(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith("688"):
        return "STAR"
    if code.startswith("30"):
        return "GEM"
    if code.startswith(("8", "4", "92")):
        return "BSE"
    return "MAIN"


# --------------------------------------------------------------------------
# sqlite
# --------------------------------------------------------------------------
def connect(db_path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    path = Path(db_path)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _clean(value: Any) -> Any:
    """Convert numpy/pandas scalars to sqlite-bindable Python values."""
    if value is None:
        return None
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def upsert_frame(
    conn: sqlite3.Connection,
    table: str,
    df: pd.DataFrame,
    keys: Iterable[str],
    chunk: int = 2000,
) -> int:
    """INSERT OR REPLACE a DataFrame into ``table`` using the frame columns."""
    if df is None or df.empty:
        return 0
    cols = list(df.columns)
    sql = (
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
        f"VALUES ({','.join('?' for _ in cols)})"
    )
    rows = [tuple(_clean(v) for v in rec)
            for rec in df.itertuples(index=False, name=None)]
    with transaction(conn):
        for i in range(0, len(rows), chunk):
            conn.executemany(sql, rows[i : i + chunk])
    return len(rows)


def query_df(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=list(params))


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def _json_default(value: Any) -> Any:
    if isinstance(value, (np.generic,)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default),
                   encoding="utf-8")
    tmp.replace(p)


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def file_size_mb(path: str | Path) -> float:
    try:
        return os.path.getsize(path) / 1024 / 1024
    except OSError:
        return 0.0


class Timer:
    def __init__(self, label: str = ""):
        self.label = label
        self.t0 = time.perf_counter()

    def __enter__(self) -> "Timer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = time.perf_counter() - self.t0
        if self.label:
            print(f"[timer] {self.label}: {self.elapsed:.2f}s")


def fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return f"{value * 100:.{digits}f}%"
