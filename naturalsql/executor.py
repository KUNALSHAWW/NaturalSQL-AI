"""Read-only query execution: the second, independent safety layer.

The AST guard decides what *should* run. This module makes sure that even if the guard were
bypassed, the database refuses to write:

* SQLite  : the file is opened with ``mode=ro`` (an OS-level read-only open) and
            ``PRAGMA query_only=ON``; a progress handler interrupts long queries
* MySQL   : the session is set ``READ ONLY`` with ``MAX_EXECUTION_TIME``
* Postgres: ``default_transaction_read_only`` and ``statement_timeout`` are set at connect time

Results are capped (``max_rows``), PII columns are masked, and errors are reduced to a short
message so database internals do not leak back into prompts or the UI.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import StaticPool

from .pii import Masker


class QueryError(RuntimeError):
    """Execution failed; the message is safe to show to users and models."""


@dataclass
class ResultSet:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    elapsed_s: float = 0.0
    masked_columns: list[str] = field(default_factory=list)
    ordered: bool = False

    def __len__(self) -> int:
        return len(self.rows)

    def fingerprint(self) -> str:
        """Canonical hash of the result, used to compare queries by *what they return*.

        Row order is ignored unless the query had an ORDER BY; floats are rounded so that
        equivalent aggregations written differently still match.
        """
        def norm(v):
            if isinstance(v, float):
                return round(v, 4)
            return v if v is None or isinstance(v, (int, str, bytes)) else str(v)

        rows = [tuple(norm(v) for v in r) for r in self.rows]
        if not self.ordered:
            rows = sorted(rows, key=lambda r: tuple(str(x) for x in r))
        payload = repr((len(self.columns), rows)).encode()
        return hashlib.sha1(payload).hexdigest()[:16]


def _sqlite_path(url: str) -> str:
    u = make_url(url)
    return str(Path(u.database).resolve()) if u.database not in (None, "", ":memory:") else ":memory:"


def build_readonly_engine(db_url: str, timeout_s: float = 10.0) -> Engine:
    """Create an engine whose connections cannot modify data."""
    url = make_url(db_url)
    backend = url.get_backend_name()
    if backend == "sqlite":
        path = _sqlite_path(db_url)
        if path == ":memory:":
            raise ValueError("an in-memory SQLite database cannot be opened read-only; use a file")
        uri = Path(path).as_uri() + "?mode=ro"

        def creator() -> sqlite3.Connection:
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.execute("PRAGMA query_only = ON")
            return conn

        return create_engine("sqlite://", creator=creator, poolclass=StaticPool)

    engine = create_engine(db_url, pool_pre_ping=True)
    if backend == "mysql":
        @event.listens_for(engine, "connect")
        def _mysql_ro(dbapi_conn, _):  # pragma: no cover - needs a MySQL server
            cur = dbapi_conn.cursor()
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME={int(timeout_s * 1000)}")
            cur.close()
    elif backend in ("postgresql", "postgres"):
        @event.listens_for(engine, "connect")
        def _pg_ro(dbapi_conn, _):  # pragma: no cover - needs a Postgres server
            cur = dbapi_conn.cursor()
            cur.execute("SET default_transaction_read_only = on")
            cur.execute(f"SET statement_timeout = {int(timeout_s * 1000)}")
            cur.close()
    return engine


class ReadOnlyExecutor:
    def __init__(self, db_url: str, timeout_s: float = 10.0, max_rows: int = 1000, masker: Masker | None = None):
        self.db_url = db_url
        self.timeout_s = timeout_s
        self.max_rows = max_rows
        self.masker = masker or Masker()
        self.engine = build_readonly_engine(db_url, timeout_s)
        self.backend = self.engine.dialect.name

    @property
    def dialect(self) -> str:
        return {"postgresql": "postgres"}.get(self.backend, self.backend)

    def run(self, sql: str) -> ResultSet:
        t0 = time.perf_counter()
        ordered = bool(re.search(r"\border\s+by\b", sql, re.IGNORECASE))
        try:
            with self.engine.connect() as conn:
                raw = conn.connection.dbapi_connection if hasattr(conn.connection, "dbapi_connection") else conn.connection
                deadline = time.monotonic() + self.timeout_s
                if self.backend == "sqlite":
                    raw.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20_000)
                try:
                    result = conn.execute(text(sql))
                    cols = list(result.keys())
                    rows = result.fetchmany(self.max_rows + 1)
                finally:
                    if self.backend == "sqlite":
                        raw.set_progress_handler(None, 0)
        except Exception as e:  # noqa: BLE001
            raise QueryError(self._short(e)) from None
        truncated = len(rows) > self.max_rows
        rows = [tuple(r) for r in rows[: self.max_rows]]
        rows, masked = self.masker.apply(cols, rows)
        return ResultSet(cols, rows, truncated, time.perf_counter() - t0, masked, ordered)

    @staticmethod
    def _short(e: Exception) -> str:
        msg = str(getattr(e, "orig", e)).splitlines()[0]
        if "interrupted" in msg.lower():
            return "query exceeded the time limit"
        msg = re.sub(r"\[SQL:.*", "", msg).strip()
        return msg[:200]
