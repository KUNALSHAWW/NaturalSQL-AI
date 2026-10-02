import pytest
from fastapi.testclient import TestClient

from naturalsql.api import create_app
from naturalsql.llm import FakeLLM
from naturalsql.memory import QueryMemory

from .conftest import make_engine


@pytest.fixture()
def client(executor, schema, tmp_path, monkeypatch):
    monkeypatch.delenv("NATURALSQL_API_KEYS", raising=False)
    llm = FakeLLM(lambda m, t: "SELECT COUNT(*) FROM customers")
    engine = make_engine(executor, schema, llm)
    engine.memory = QueryMemory(tmp_path / "m.db")
    return TestClient(create_app(lambda: engine)), engine


def test_health_and_schema(client):
    c, _ = client
    h = c.get("/health").json()
    assert h["status"] == "ok" and h["dialect"] == "sqlite" and h["tables"] == 7
    s = c.get("/schema").json()
    assert s["tables"]["orders"]["rows"] == 500


def test_ask_returns_rows_explanation_and_candidates(client):
    c, _ = client
    r = c.post("/ask", json={"question": "How many customers?"}).json()
    assert r["status"] == "ok" and r["rows"] == [[120]] and r["explanation"] and len(r["candidates"]) == 1
    assert r["tokens"]["llm_calls"] == 1


def test_ask_validates_input(client):
    c, _ = client
    assert c.post("/ask", json={"question": ""}).status_code == 422
    assert c.post("/ask", json={"question": "x", "n_candidates": 99}).status_code == 422


def test_check_sql_endpoint_exposes_the_guard(client):
    c, _ = client
    bad = c.post("/check-sql", json={"sql": "DROP TABLE customers"}).json()
    assert bad["allowed"] is False and bad["reasons"]
    ok = c.post("/check-sql", json={"sql": "SELECT name FROM customers"}).json()
    assert ok["allowed"] and ok["normalised_sql"].endswith("LIMIT 1000") and ok["tables"] == ["customers"]


def test_feedback_stores_only_guard_approved_sql(client):
    c, engine = client
    r = c.post("/feedback", json={"question": "count customers", "sql": "SELECT COUNT(*) FROM customers"})
    assert r.json() == {"stored": True, "verified_examples": 1}
    assert c.post("/feedback", json={"question": "evil", "sql": "DROP TABLE customers"}).status_code == 422
    assert engine.memory.count(engine.db_key) == 1


def test_audit_endpoint(client):
    c, _ = client
    c.post("/ask", json={"question": "How many customers?"})
    assert c.get("/audit").status_code == 200


def test_api_key_required_when_configured(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("NATURALSQL_API_KEYS", "s3cret,other")
    assert c.post("/ask", json={"question": "q"}).status_code == 401
    assert c.post("/ask", json={"question": "q"}, headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.post("/ask", json={"question": "How many customers?"}, headers={"X-API-Key": "s3cret"}).status_code == 200
    assert c.get("/health").status_code == 200       # health stays open for probes
