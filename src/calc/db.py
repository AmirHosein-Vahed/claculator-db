"""SQLite persistence for calculation history.

The schema is created on demand, so there is no migration step and no separate
init container: the first invocation in a fresh volume creates the table.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path

DEFAULT_DB_PATH = "calc.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calculations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_calc_created_at ON calculations(created_at);
"""

_COLUMNS = "id, expression, result, created_at"


class StorageError(RuntimeError):
    """Raised when the database cannot be opened, read, or written."""


@dataclass(frozen=True)
class Calculation:
    """A single stored calculation."""

    id: int
    expression: str
    result: str
    created_at: str


def database_path() -> Path:
    """Location of the SQLite file, from ``CALC_DB`` or the working directory."""
    return Path(os.environ.get("CALC_DB") or DEFAULT_DB_PATH)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as exc:
        raise StorageError(
            f"could not open database at {path}: {exc} "
            f"(does the directory exist and is it writable?)"
        ) from exc

    try:
        connection.row_factory = sqlite3.Row
        connection.executescript(_SCHEMA)
        yield connection
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StorageError(f"database error at {path}: {exc}") from exc
    finally:
        connection.close()


def _to_calculation(row: sqlite3.Row) -> Calculation:
    return Calculation(**dict(row))


def save(expression: str, result: str) -> Calculation:
    """Insert one calculation and return the stored record."""
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO calculations (expression, result) VALUES (?, ?)",
            (expression, result),
        )
        row = connection.execute(
            f"SELECT {_COLUMNS} FROM calculations WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _to_calculation(row)


def history(limit: int = 20) -> list[Calculation]:
    """Return up to ``limit`` calculations, most recent first."""
    limit = max(1, limit)
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT {_COLUMNS} FROM calculations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_to_calculation(row) for row in rows]


def get(identifier: int) -> Calculation | None:
    """Return a single calculation by id, or ``None`` if it does not exist."""
    with _connect() as connection:
        row = connection.execute(
            f"SELECT {_COLUMNS} FROM calculations WHERE id = ?",
            (identifier,),
        ).fetchone()
    return _to_calculation(row) if row is not None else None


def clear() -> int:
    """Delete all calculations and return how many rows were removed."""
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM calculations")
        return cursor.rowcount
