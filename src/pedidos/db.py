"""Runs the LLM's queries on a read-only, locked-down connection.

This is the second line of defense: even if a dangerous query got past the validator
(sql_guard), SQLite itself would reject it.
- The database is opened read-only (mode=ro).
- An authorizer only allows SELECT, reading the allowed tables and harmless functions.
- A progress handler cancels queries that exceed the time limit.
- The size of each value and the number of returned rows are capped.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pedidos.errors import (
    DatabaseUnavailableError,
    QueryExecutionError,
    QueryTimeoutError,
    UnsafeQueryError,
)
from pedidos.sql_guard import ALLOWED_TABLES, DENIED_FUNCTIONS

MAX_VALUE_LENGTH = 1_000_000  # bytes per text or blob value: avoids exhausting memory
PROGRESS_STEPS = 1_000  # how many SQLite instructions run between time checks


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool


def _authorize(action: int, arg1: str | None, arg2: str | None, db_name: str | None, _: str | None) -> int:
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:  # arg1 = table being read; views read 'pedidos' internally
        # COUNT(*) arrives without a database name (None). No other database can be attached,
        # because ATTACH is denied.
        allowed = db_name in (None, "main") and (arg1 or "").lower() in ALLOWED_TABLES
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:  # arg2 = function name
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() in DENIED_FUNCTIONS else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY  # writes, DDL, PRAGMA, ATTACH, transactions, recursive CTEs...


def connect_read_only(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise DatabaseUnavailableError(f"No existe la base de datos {db_path}. Créala con: make etl")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_LENGTH)
    conn.set_authorizer(_authorize)
    return conn


def run_query(db_path: Path, sql: str, *, max_rows: int = 500, timeout_s: float = 5.0) -> QueryResult:
    """Runs a query and returns at most max_rows rows (truncated says whether there were more)."""
    conn = connect_read_only(db_path)
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), PROGRESS_STEPS)
    try:
        cursor = conn.execute(sql)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
    except sqlite3.Error as error:
        raise _translate(error) from error
    finally:
        conn.close()
    return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)


def _translate(error: sqlite3.Error) -> Exception:
    name = getattr(error, "sqlite_errorname", "")
    if name == "SQLITE_INTERRUPT":
        return QueryTimeoutError("La consulta ha tardado demasiado y se ha cancelado.")
    # A function denied by the authorizer arrives as SQLITE_ERROR with the text "not authorized".
    denied = name in {"SQLITE_AUTH", "SQLITE_READONLY"} or "not authorized" in str(error)
    if denied or isinstance(error, sqlite3.ProgrammingError):  # ProgrammingError: several statements
        return UnsafeQueryError(
            "La base de datos ha rechazado la consulta: solo se permite una lectura de las tablas permitidas."
        )
    return QueryExecutionError(f"La consulta no se ha podido ejecutar: {error}")
