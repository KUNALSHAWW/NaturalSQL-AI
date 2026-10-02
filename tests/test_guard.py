import json

import pytest

from naturalsql.bench.evaluate import bench_policy, evaluate_guard, load_adversarial, load_questions
from naturalsql.guard import SQLGuard

ATTACKS = load_adversarial()
POLICY = bench_policy()
COLUMNS = {
    "users": {"id", "email", "password_hash", "role"},
    "employees": {"id", "name", "department", "salary", "hire_date", "manager_id", "ssn"},
    "customers": {"id", "name", "email", "country", "segment", "signup_date"},
}


def guard(dialect="sqlite", **kw):
    return SQLGuard(dialect=dialect, table_columns=COLUMNS, **{**POLICY, **kw})


@pytest.mark.parametrize("attack", ATTACKS, ids=[f"{a['category']}-{i}" for i, a in enumerate(ATTACKS)])
def test_every_attack_payload_is_blocked(attack):
    result = guard(attack["dialect"]).check(attack["sql"])
    assert not result.ok, f"NOT BLOCKED: {attack['sql']!r}"
    assert result.reasons and result.sql == ""


def test_attack_corpus_covers_all_major_classes():
    cats = {a["category"] for a in ATTACKS}
    assert {"destructive", "stacked_statements", "obfuscation", "hidden_dml", "file_os_access",
            "denial_of_service", "catalog_exfiltration", "privilege_session", "policy_violation", "malformed"} <= cats
    assert len(ATTACKS) >= 100


@pytest.mark.parametrize("q", load_questions(), ids=lambda q: f"gold-{q['id']}")
def test_legitimate_queries_pass(q):
    r = guard().check(q["gold_sql"])
    assert r.ok, r.reason


def test_corpus_evaluation_summary(db_path):
    res = evaluate_guard(db_path)
    assert res["block_rate"] == 1.0 and res["missed"] == []
    assert res["false_positive_rate"] == 0.0


def test_limit_is_injected_and_capped():
    g = guard(max_rows=50)
    assert g.check("SELECT * FROM customers").sql.endswith("LIMIT 50")
    assert g.check("SELECT * FROM customers LIMIT 5").sql.endswith("LIMIT 5")
    assert g.check("SELECT * FROM customers LIMIT 99999").sql.endswith("LIMIT 50")
    assert g.check("SELECT id FROM customers UNION SELECT id FROM employees").sql.endswith("LIMIT 50")


def test_executed_sql_is_regenerated_without_comments():
    r = guard().check("SELECT name /* sneaky */ FROM customers -- trailing\n")
    assert r.ok and "sneaky" not in r.sql and "trailing" not in r.sql


def test_select_star_blocked_on_tables_with_restricted_columns():
    assert not guard().check("SELECT * FROM users").ok
    assert not guard().check("SELECT * FROM employees").ok
    assert guard().check("SELECT name, department FROM employees").ok
    assert guard().check("SELECT COUNT(*) FROM users").ok          # COUNT(*) reads no restricted data


def test_qualified_denied_column_syntax():
    g = guard(denied_columns={"customers.email"})
    assert not g.check("SELECT c.email FROM customers c").ok
    assert g.check("SELECT c.name FROM customers c").ok


def test_cte_names_are_not_mistaken_for_tables():
    r = guard().check("WITH big AS (SELECT * FROM orders WHERE total > 100) SELECT COUNT(*) FROM big")
    assert r.ok and r.tables == {"orders"}


def test_table_allow_list():
    g = guard(allowed_tables={"customers"})
    assert g.check("SELECT * FROM customers").ok
    r = g.check("SELECT * FROM orders")
    assert not r.ok and "not available" in r.reason


def test_complexity_limits():
    joins = " ".join(f"JOIN customers c{i} ON c{i}.id = c.id" for i in range(10))
    assert not guard().check(f"SELECT c.id FROM customers c {joins}").ok
    assert guard().check("SELECT c.id FROM customers c JOIN orders o ON o.customer_id = c.id").ok


def test_function_blocked_by_emitted_name_even_when_sqlglot_renames_it():
    assert not guard("postgres").check("SELECT version()").ok
    assert not guard("sqlite").check("SELECT sqlite_version()").ok
    assert not guard("postgres").check("SELECT * FROM generate_series(1, 5)").ok


def test_mysql_executable_comment_rejected_outright():
    r = guard("mysql").check("SELECT 1 /*!50000 UNION SELECT password FROM mysql.user */")
    assert not r.ok and "executable" in r.reason


def test_reasons_are_human_readable():
    r = guard().check("DROP TABLE customers")
    assert not r.ok and "read-only" in r.reason.lower()
    r = guard().check("SELECT 1; SELECT 2")
    assert "exactly one statement" in r.reason


def test_dialects_parse_their_own_syntax():
    assert guard("mysql").check("SELECT DATE_FORMAT(created_at, '%Y') FROM orders").ok
    assert guard("postgres").check("SELECT EXTRACT(YEAR FROM created_at::date) FROM orders").ok
    assert guard("sqlite").check("SELECT strftime('%Y', created_at) FROM orders").ok


def test_json_corpus_is_valid():
    for a in ATTACKS:
        assert set(a) == {"category", "dialect", "sql", "note"}
    json.dumps(ATTACKS)
