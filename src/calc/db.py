import os
import psycopg2
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterator

@dataclass(frozen=True)
class Calculation:
    id: int
    expression: str
    result: str
    created_at: str

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "password"),
        dbname=os.environ.get("DB_NAME", "postgres")
    )

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calculations (
    id         SERIAL PRIMARY KEY,
    expression TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

@contextmanager
def _connect() -> Iterator:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA)
            conn.commit()
        yield conn
    finally:
        conn.close()

def save(expression: str, result: str) -> Calculation:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO calculations (expression, result) VALUES (%s, %s) RETURNING id, expression, result, created_at",
                (expression, result)
            )
            row = cur.fetchone()
            conn.commit()
            return Calculation(id=row[0], expression=row[1], result=row[2], created_at=str(row[3]))

def history(limit: int = 20) -> list[Calculation]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, expression, result, created_at FROM calculations ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            return [Calculation(id=r[0], expression=r[1], result=r[2], created_at=str(r[3])) for r in rows]

def get(identifier: int) -> Calculation | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, expression, result, created_at FROM calculations WHERE id = %s", (identifier,))
            row = cur.fetchone()
            return Calculation(id=row[0], expression=row[1], result=row[2], created_at=str(row[3])) if row else None

def clear() -> int:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM calculations")
            conn.commit()
            return cur.rowcount
