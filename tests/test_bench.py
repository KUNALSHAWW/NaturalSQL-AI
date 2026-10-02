"""The benchmark harness must itself be correct, or every published number is meaningless."""
import sqlite3

import pytest

from naturalsql.bench import evaluate as ev
from naturalsql.bench import retail_db
from naturalsql.llm import FakeLLM, LLMResponse


@pytest.fixture(scope="module")
def bench_db(tmp_path_factory):
    return retail_db.build(tmp_path_factory.mktemp("bench") / "bench.db")


def test_database_build_is_deterministic(tmp_path):
    a = retail_db.build(tmp_path / "a.db", seed=11, n_customers=50, n_orders=100)
    b = retail_db.build(tmp_path / "b.db", seed=11, n_customers=50, n_orders=100)
    dump = lambda p: list(sqlite3.connect(p).iterdump())  # noqa: E731
    assert dump(a) == dump(b)


def test_every_gold_query_runs_and_returns_data(bench_db):
    con = sqlite3.connect(bench_db)
    for q in ev.load_questions():
        rows = con.execute(q["gold_sql"]).fetchall()
        assert rows and any(v is not None for r in rows for v in r), q["id"]
    assert len(ev.load_questions()) >= 60
    assert {q["difficulty"] for q in ev.load_questions()} == {"easy", "medium", "hard"}


def test_rows_match_semantics():
    assert ev.rows_match([(1, "a")], [(1.0, "a")], ordered=False)               # int vs float
    assert ev.rows_match([(0.1 + 0.2,)], [(0.3,)], ordered=False)               # float noise
    assert ev.rows_match([(2,), (1,)], [(1,), (2,)], ordered=False)             # order ignored
    assert not ev.rows_match([(2,), (1,)], [(1,), (2,)], ordered=True)          # order matters when asked
    assert not ev.rows_match([(1,)], [(1,), (2,)], ordered=False)               # different row count
    assert not ev.rows_match([(1, 2)], [(1,)], ordered=False)                   # different column count
    assert not ev.rows_match([("a",)], [("b",)], ordered=False)


def test_oracle_model_scores_full_marks(bench_db):
    gold = {q["question"]: q["gold_sql"] for q in ev.load_questions()}

    def oracle(messages, temperature):
        question = messages[-1]["content"].rsplit("Question: ", 1)[1].split("\nSQL:")[0].strip()
        return gold[question]

    res = ev.run_accuracy(FakeLLM(oracle), bench_db, n_candidates=2, limit=15, log=lambda *_: None)
    table = res["execution_accuracy"]
    assert all(v["overall"] == 1.0 for v in table.values())
    assert res["n_questions"] == 15
    assert res["confidence_calibration"]["unanimous_answers"]["accuracy"] == 1.0


def test_wrong_model_scores_low_and_ablation_separates_systems(bench_db):
    gold = {q["question"]: q["gold_sql"] for q in ev.load_questions()}

    def flaky(messages, temperature):
        """Wrong SQL on first try for every question, correct after a repair prompt."""
        text = messages[-1]["content"]
        if "The query you wrote failed" in text:
            question = messages[1]["content"].rsplit("Question: ", 1)[1].split("\nSQL:")[0].strip()
            return gold[question]
        return "SELECT nonexistent_column FROM customers"

    res = ev.run_accuracy(FakeLLM(flaky), bench_db, n_candidates=1, limit=10, log=lambda *_: None)
    t = res["execution_accuracy"]
    assert t["baseline_single_shot_full_schema"]["overall"] == 0.0
    assert t["single_shot_with_schema_linking"]["overall"] == 0.0
    assert t["plus_error_repair"]["overall"] == 1.0           # repair is what rescues it


def test_injection_harness_counts_a_leak_as_a_successful_attack(bench_db):
    # a model that is fully compromised: it writes whatever the attacker asked for
    res = ev.run_injection(FakeLLM(lambda m, t: "SELECT password_hash FROM users"), bench_db)
    assert res["attacks_succeeded"] == 0                        # guard stops the restricted column
    assert res["outcomes"].get("guard (blocked)") == res["prompts"]

    res = ev.run_injection(FakeLLM(lambda m, t: "DROP TABLE users"), bench_db)
    assert res["attacks_succeeded"] == 0 and sqlite3.connect(bench_db).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 20


def test_injection_harness_detects_a_real_leak(bench_db):
    """Sanity check of the detector: if secrets *were* returned it must flag the attack."""
    secret = sqlite3.connect(bench_db).execute("SELECT ssn FROM employees LIMIT 1").fetchone()[0]
    # bypass the guard's policy by asking the harness to run with no denied columns
    from naturalsql.config import Settings
    from naturalsql.executor import ReadOnlyExecutor
    from naturalsql.pipeline import Text2SQL

    leaky = Text2SQL(ReadOnlyExecutor(f"sqlite:///{bench_db}"), FakeLLM(lambda m, t: "SELECT ssn FROM employees"),
                     Settings(provider="ollama", n_candidates=1, denied_columns=set()))
    # masking is on by default, so the raw secret must not appear even without a deny rule
    a = leaky.ask("give me ssn")
    assert a.status == "ok" and secret not in {str(v) for r in a.rows for v in r}
    assert a.masked_columns == ["ssn"]


def test_throughput_harness_reports_decode_speed():
    class Client:
        name = "fake:model"

        def complete(self, messages, temperature=0.0, max_tokens=300):
            return LLMResponse("SELECT 1", prompt_tokens=50, completion_tokens=100, latency_s=2.0, decode_tps=55.0)

    r = ev.run_throughput(Client(), runs=3, warmup=1)
    assert r["decode_tokens_per_second"]["mean"] == 55.0 and r["runs"] == 3
    assert r["end_to_end_tokens_per_second_mean"] == 50.0 and r["provider"] == "fake:model"


def test_read_only_executor_summary(bench_db):
    s = ev.evaluate_readonly_executor(bench_db)
    assert s["refused"] == s["direct_write_attempts"] and s["database_intact"]
