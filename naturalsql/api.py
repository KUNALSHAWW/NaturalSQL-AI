"""REST API: ``uvicorn naturalsql.api:app``.

Environment:
    NATURALSQL_DB_URL, NATURALSQL_PROVIDER, NATURALSQL_MODEL, GROQ_API_KEY / OPENAI_API_KEY,
    NATURALSQL_DENIED_COLUMNS, NATURALSQL_ALLOWED_TABLES
    NATURALSQL_API_KEYS : comma-separated keys. When set, every request must send ``X-API-Key``.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .audit import AuditLog
from .config import Settings
from .executor import ReadOnlyExecutor
from .guard import SQLGuard
from .llm import make_client
from .memory import QueryMemory
from .pii import Masker
from .pipeline import Answer, Text2SQL


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    n_candidates: int | None = Field(None, ge=1, le=7)
    user: str = "api"


class FeedbackRequest(BaseModel):
    question: str
    sql: str
    verified: bool = True


class CheckRequest(BaseModel):
    sql: str = Field(max_length=20000)


def answer_to_dict(a: Answer, include_candidates: bool = True) -> dict:
    out = {
        "status": a.status,
        "question": a.question,
        "sql": a.sql,
        "columns": a.columns,
        "rows": [list(r) for r in a.rows],
        "truncated": a.truncated,
        "confidence": a.confidence,
        "agreement": a.agreement,
        "explanation": a.explanation,
        "chart": a.chart,
        "message": a.message,
        "masked_columns": a.masked_columns,
        "linked_tables": a.linked_tables,
        "latency_s": round(a.latency_s, 3),
        "tokens": {"prompt": a.prompt_tokens, "completion": a.completion_tokens, "llm_calls": a.llm_calls},
    }
    if include_candidates:
        out["candidates"] = [
            {"sql": c.sql, "source": c.source, "valid": c.valid, "error": c.error, "security_block": c.security_block}
            for c in a.candidates
        ]
    return out


def build_engine(settings: Settings | None = None, llm=None) -> Text2SQL:
    settings = settings or Settings.from_env()
    executor = ReadOnlyExecutor(settings.db_url, settings.timeout_s, settings.max_rows, Masker(settings.mask_patterns))
    return Text2SQL(
        executor,
        llm or make_client(settings),
        settings,
        memory=QueryMemory(settings.memory_path),
        audit=AuditLog(settings.audit_path),
        db_key=settings.db_url,
    )


def create_app(engine_factory=None) -> FastAPI:
    app = FastAPI(
        title="NaturalSQL API", version="2.0.0",
        description="Ask questions in English; every generated query is parsed, validated and run read-only.",
    )
    factory = engine_factory or (lambda: build_engine())

    @lru_cache(maxsize=1)
    def engine() -> Text2SQL:
        return factory()

    def auth(x_api_key: str | None = Header(None)) -> None:
        keys = [k for k in os.environ.get("NATURALSQL_API_KEYS", "").split(",") if k]
        if keys and not any(secrets.compare_digest(x_api_key or "", k) for k in keys):
            raise HTTPException(401, "missing or invalid API key")

    @app.get("/health")
    def health() -> dict:
        e = engine()
        return {"status": "ok", "dialect": e.executor.dialect, "tables": len(e.schema.tables), "model": getattr(e.llm, "name", "")}

    @app.get("/schema", dependencies=[Depends(auth)])
    def schema() -> dict:
        e = engine()
        return {
            "dialect": e.schema.dialect,
            "tables": {
                n: {"rows": t.row_count, "columns": [{"name": c.name, "type": c.type, "primary_key": c.primary_key} for c in t.columns]}
                for n, t in e.schema.tables.items()
            },
        }

    @app.post("/ask", dependencies=[Depends(auth)])
    def ask(req: AskRequest) -> dict:
        return answer_to_dict(engine().ask(req.question, user=req.user, n_candidates=req.n_candidates))

    @app.post("/check-sql", dependencies=[Depends(auth)])
    def check_sql(req: CheckRequest) -> dict:
        """Run the guard on arbitrary SQL without executing it."""
        g: SQLGuard = engine().guard
        r = g.check(req.sql)
        return {"allowed": r.ok, "normalised_sql": r.sql, "reasons": r.reasons, "tables": sorted(r.tables)}

    @app.post("/feedback", dependencies=[Depends(auth)])
    def feedback(req: FeedbackRequest) -> dict:
        e = engine()
        if not req.verified:
            return {"stored": False}
        if e.memory is None:
            raise HTTPException(409, "query memory is not enabled on this server")
        g = e.guard.check(req.sql)
        if not g.ok:
            raise HTTPException(422, "only SQL that passes the guard can be stored: " + g.reason)
        e.memory.add(req.question, g.sql, e.db_key)
        return {"stored": True, "verified_examples": e.memory.count(e.db_key)}

    @app.get("/audit", dependencies=[Depends(auth)])
    def audit(n: int = Query(50, ge=1, le=500)) -> list[dict]:
        audit_log = engine().audit
        return audit_log.recent(n) if audit_log else []

    return app


app = create_app()
