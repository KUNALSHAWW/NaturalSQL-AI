import httpx
import pytest

from naturalsql.config import Settings
from naturalsql.explain import explain_sql, suggest_chart
from naturalsql.llm import FakeLLM, LLMError, OllamaClient, OpenAICompatClient, make_client, strip_reasoning
from naturalsql.memory import QueryMemory


# ---------------------------------------------------------------- explain / chart
def test_explanation_describes_the_query_without_a_model():
    bullets = explain_sql(
        "SELECT c.country, SUM(o.total) AS revenue FROM customers c JOIN orders o ON o.customer_id = c.id "
        "WHERE o.status = 'delivered' GROUP BY c.country HAVING SUM(o.total) > 100 ORDER BY revenue DESC LIMIT 5"
    )
    text = " ".join(bullets)
    assert "customers, orders (joined)" in text and "total o.total" in text
    assert "status = 'delivered'" in text and "Grouped by c.country" in text and "descending" in text
    assert "at most 5 rows" in text and "Keeps groups where" in text


def test_explanation_is_empty_for_unparseable_sql():
    assert explain_sql("not sql at all ((") == []


def test_chart_suggestions():
    assert suggest_chart(["n"], [(5,)])["type"] == "metric"
    assert suggest_chart(["country", "n"], [("A", 1), ("B", 2)]) == {"type": "bar", "x": "country", "y": "n"}
    assert suggest_chart(["month", "n"], [("2024-01", 1), ("2024-02", 2)])["type"] == "line"
    assert suggest_chart(["a", "b", "c"], [("x", "y", "z")])["type"] == "table"
    assert suggest_chart(["a"], [])["type"] == "none"


# ---------------------------------------------------------------- memory
def test_memory_retrieves_the_most_similar_verified_question(tmp_path):
    m = QueryMemory(tmp_path / "m.db")
    m.add("How many customers are in each country?", "SELECT country, COUNT(*) FROM customers GROUP BY country")
    m.add("What is the average product price?", "SELECT AVG(price) FROM products")
    hit = m.retrieve("Count the customers in every country")
    assert hit and "GROUP BY country" in hit[0].sql and hit[0].similarity > 0.35
    assert m.retrieve("totally unrelated astronomy question") == []


def test_memory_is_scoped_per_database_and_upserts(tmp_path):
    m = QueryMemory(tmp_path / "m.db")
    m.add("q one", "SELECT 1", db_key="a")
    m.add("q one", "SELECT 2", db_key="a")
    m.add("q one", "SELECT 3", db_key="b")
    assert m.count("a") == 1 and m.count("b") == 1
    assert m.all("a")[0].sql == "SELECT 2"


# ---------------------------------------------------------------- llm
def test_reasoning_blocks_are_removed():
    assert strip_reasoning("<think>plan</think>\nSELECT 1") == "SELECT 1"


def test_fake_llm_script_and_calls():
    llm = FakeLLM(["a", "b"])
    assert llm.complete([{"role": "user", "content": "x"}]).text == "a"
    assert llm.complete([{"role": "user", "content": "x"}]).text == "b"
    assert llm.complete([{"role": "user", "content": "x"}]).text == "b"
    assert len(llm.calls) == 3


def test_openai_compatible_client_parses_usage(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions") and headers["Authorization"] == "Bearer k"
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": "<think>x</think>SELECT 1"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4}})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = OpenAICompatClient("https://api.example/v1", "k", "m").complete([{"role": "user", "content": "q"}])
    assert r.text == "SELECT 1" and (r.prompt_tokens, r.completion_tokens) == (11, 4) and r.tokens_per_second > 0


def test_ollama_client_uses_server_timings(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/api/chat") and json["think"] is False
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "message": {"content": "SELECT 1"}, "eval_count": 50, "eval_duration": 2_000_000_000, "prompt_eval_count": 90})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = OllamaClient("gemma").complete([{"role": "user", "content": "q"}])
    assert r.decode_tps == 25.0 and r.completion_tokens == 50 and r.prompt_tokens == 90


def test_http_errors_become_llm_errors(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(LLMError):
        OpenAICompatClient("http://x", "k", "m").complete([{"role": "user", "content": "q"}])


def test_make_client_requires_a_key_for_hosted_providers():
    with pytest.raises(LLMError, match="API key"):
        make_client(Settings(provider="groq", api_key=""))
    assert make_client(Settings(provider="ollama")).name.startswith("ollama:")
    assert make_client(Settings(provider="groq", api_key="k")).name.startswith("groq:")


def test_settings_defaults_per_provider():
    s = Settings(provider="groq")
    assert s.base_url.startswith("https://api.groq.com") and s.model
    assert Settings(provider="ollama").parallel is False


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("NATURALSQL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NATURALSQL_DENIED_COLUMNS", "ssn, salary")
    s = Settings.from_env()
    assert s.provider == "openai" and s.api_key == "sk-test" and s.denied_columns == {"ssn", "salary"}
