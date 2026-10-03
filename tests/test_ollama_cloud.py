import httpx
import pytest

from naturalsql.config import Settings
from naturalsql.llm import LLMError, OllamaClient, make_client


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "ok"}, "eval_count": 3, "eval_duration": 1_000_000_000, "prompt_eval_count": 5}


def test_cloud_provider_defaults_and_alias(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "key-from-env")
    s = Settings(provider="ollama-cloud")
    assert s.provider == "ollama_cloud" and s.base_url == "https://ollama.com"
    assert s.model and s.api_key == "key-from-env"


def test_cloud_requires_a_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OLLAMA_API_KEY"):
        make_client(Settings(provider="ollama_cloud"))


def test_cloud_request_is_authenticated_and_omits_think(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = make_client(Settings(provider="ollama_cloud", api_key="secret", model="deepseek-v3.1:671b"))
    r = client.complete([{"role": "user", "content": "hi"}])
    assert seen["url"] == "https://ollama.com/api/chat"
    assert seen["headers"] == {"Authorization": "Bearer secret"}
    assert seen["json"]["model"] == "deepseek-v3.1:671b" and "think" not in seen["json"]
    assert r.text == "ok" and client.name == "ollama-cloud:deepseek-v3.1:671b"


def test_local_ollama_sends_no_auth_header(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(headers=headers, json=json)
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    OllamaClient("gemma4:e4b").complete([{"role": "user", "content": "hi"}])
    assert seen["headers"] == {} and seen["json"]["think"] is False
