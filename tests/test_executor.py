import sqlite3

import pytest

from naturalsql.executor import QueryError, ReadOnlyExecutor, ResultSet
from naturalsql.pii import Masker


def test_writes_are_refused_even_when_the_guard_is_bypassed(db_path):
    ex = ReadOnlyExecutor(f"sqlite:///{db_path}")
    before = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    for stmt in ("DELETE FROM customers", "DROP TABLE orders", "UPDATE products SET price = 0",
                 "INSERT INTO categories VALUES (99, 'x')", "CREATE TABLE evil (x int)", "ALTER TABLE users ADD COLUMN z TEXT"):
        with pytest.raises(QueryError):
            ex.run(stmt)
    assert sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before


def test_reads_work_and_report_columns(executor):
    r = executor.run("SELECT id, country FROM customers ORDER BY id LIMIT 3")
    assert r.columns == ["id", "country"] and len(r) == 3 and r.ordered


def test_row_cap_sets_truncated_flag(db_path):
    ex = ReadOnlyExecutor(f"sqlite:///{db_path}", max_rows=10)
    r = ex.run("SELECT * FROM orders")
    assert len(r) == 10 and r.truncated


def test_runaway_query_is_interrupted(db_path):
    ex = ReadOnlyExecutor(f"sqlite:///{db_path}", timeout_s=0.5)
    slow = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT COUNT(*) FROM r"
    with pytest.raises(QueryError, match="time limit"):
        ex.run(slow)
    assert ex.run("SELECT 1").rows == [(1,)]      # the executor still works afterwards


def test_errors_are_short_and_do_not_leak_sql(executor):
    with pytest.raises(QueryError) as e:
        executor.run("SELECT nonexistent FROM customers")
    assert "nonexistent" in str(e.value) and "[SQL:" not in str(e.value) and len(str(e.value)) < 220


def test_pii_columns_are_masked(executor):
    r = executor.run("SELECT name, email FROM customers LIMIT 2")
    assert r.masked_columns == ["email"]
    assert all("***" in row[1] and "@example.com" in row[1] for row in r.rows)
    assert not any("." in row[1].split("@")[0] for row in r.rows)


def test_masker_rules():
    m = Masker()
    assert m._mask("alice@x.org", "email") == "a***@x.org"
    assert m._mask("123-45-6789", "ssn") == "*********89"
    assert m._mask("hunter2", "password") == "***"
    assert m.is_sensitive("customer_email") and m.is_sensitive("PasswordHash") and not m.is_sensitive("country")


def test_fingerprint_ignores_order_only_when_query_is_unordered():
    a = ResultSet(["x"], [(1,), (2,)], ordered=False)
    b = ResultSet(["x"], [(2,), (1,)], ordered=False)
    assert a.fingerprint() == b.fingerprint()
    c = ResultSet(["x"], [(1,), (2,)], ordered=True)
    d = ResultSet(["x"], [(2,), (1,)], ordered=True)
    assert c.fingerprint() != d.fingerprint()


def test_fingerprint_rounds_floats():
    assert ResultSet(["v"], [(0.1 + 0.2,)]).fingerprint() == ResultSet(["v"], [(0.3,)]).fingerprint()
    assert ResultSet(["v"], [(1,)]).fingerprint() != ResultSet(["v"], [(2,)]).fingerprint()


def test_in_memory_sqlite_is_rejected():
    with pytest.raises(ValueError):
        ReadOnlyExecutor("sqlite:///:memory:")
