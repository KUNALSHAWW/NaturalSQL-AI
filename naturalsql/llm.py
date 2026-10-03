"""LLM providers behind one tiny interface.

Three real backends and one test double:

* :class:`OpenAICompatClient`  Groq, OpenAI and any OpenAI-compatible server
* :class:`OllamaClient`        a local Ollama server (native API, exact token timings)
* :class:`FakeLLM`             scripted responses for tests and offline demos

Every call returns an :class:`LLMResponse` carrying token counts and wall-clock timing, so
throughput (tokens per second) is *measured* from real calls rather than assumed.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    ttft_s: float | None = None          # time to first token (streaming only)
    decode_tps: float | None = None      # decode speed after the first token, tokens per second

    @property
    def tokens_per_second(self) -> float:
        """End-to-end completion tokens per second."""
        return self.completion_tokens / self.latency_s if self.latency_s > 0 else 0.0


Messages = list[dict[str, str]]


class LLMClient(Protocol):
    name: str

    def complete(self, messages: Messages, temperature: float = 0.0, max_tokens: int = 400) -> LLMResponse: ...


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks emitted by reasoning models."""
    return _THINK.sub("", text or "").strip()


class OpenAICompatClient:
    """Chat completions over HTTP for Groq, OpenAI and compatible servers."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120.0, name: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = name or f"openai-compat:{model}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def complete(self, messages: Messages, temperature: float = 0.0, max_tokens: int = 400) -> LLMResponse:
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"{self.name}: {e}") from e
        dt = time.perf_counter() - t0
        data = r.json()
        usage = data.get("usage", {})
        return LLMResponse(
            text=strip_reasoning(data["choices"][0]["message"].get("content") or ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_s=dt,
        )

    def stream(self, messages: Messages, temperature: float = 0.0, max_tokens: int = 400) -> LLMResponse:
        """Streaming call that measures time-to-first-token and decode throughput."""
        body = {
            "model": self.model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True},
        }
        t0 = time.perf_counter()
        first = None
        chunks: list[str] = []
        usage: dict = {}
        try:
            with httpx.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=self.timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    evt = json.loads(payload)
                    if evt.get("usage"):
                        usage = evt["usage"]
                    for ch in evt.get("choices", []):
                        piece = (ch.get("delta") or {}).get("content")
                        if piece:
                            if first is None:
                                first = time.perf_counter() - t0
                            chunks.append(piece)
        except httpx.HTTPError as e:
            raise LLMError(f"{self.name}: {e}") from e
        dt = time.perf_counter() - t0
        n = usage.get("completion_tokens") or len(chunks)
        decode = (n - 1) / (dt - first) if first is not None and dt > first and n > 1 else None
        return LLMResponse(strip_reasoning("".join(chunks)), usage.get("prompt_tokens", 0), n, dt, first, decode)


class OllamaClient:
    """Ollama server, local or Ollama Cloud (``https://ollama.com`` with an API key).

    Uses the native ``/api/chat`` endpoint and Ollama's own token counters and timings. With an
    ``api_key`` the request carries ``Authorization: Bearer <key>``, which is how Ollama Cloud
    authenticates. ``think=None`` leaves the field out, which hosted reasoning models prefer.
    """

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 600.0,
                 think: bool | None = False, api_key: str = ""):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.think = think
        self.api_key = api_key
        self.name = f"{'ollama-cloud' if api_key else 'ollama'}:{model}"

    def complete(self, messages: Messages, temperature: float = 0.0, max_tokens: int = 400) -> LLMResponse:
        body = {
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if self.think is not None:
            body["think"] = self.think
        t0 = time.perf_counter()
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = httpx.post(f"{self.base_url}/api/chat", json=body, headers=headers, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"{self.name}: {e}") from e
        dt = time.perf_counter() - t0
        d = r.json()
        eval_s = (d.get("eval_duration") or 0) / 1e9
        n = d.get("eval_count", 0)
        return LLMResponse(
            text=strip_reasoning(d.get("message", {}).get("content", "")),
            prompt_tokens=d.get("prompt_eval_count", 0),
            completion_tokens=n,
            latency_s=dt,
            decode_tps=(n / eval_s) if eval_s > 0 else None,
        )


class FakeLLM:
    """Deterministic stand-in. ``script`` is a list of replies or a callable ``f(messages, temperature) -> str``."""

    name = "fake"

    def __init__(self, script: list[str] | Callable[[Messages, float], str]):
        self.script = script
        self.calls: list[tuple[Messages, float]] = []
        self._i = 0
        self._lock = threading.Lock()

    def complete(self, messages: Messages, temperature: float = 0.0, max_tokens: int = 400) -> LLMResponse:
        with self._lock:
            self.calls.append((messages, temperature))
            if callable(self.script):
                text = self.script(messages, temperature)
            else:
                text = self.script[min(self._i, len(self.script) - 1)]
                self._i += 1
        return LLMResponse(text=text, prompt_tokens=sum(len(m["content"]) // 4 for m in messages),
                           completion_tokens=max(1, len(text) // 4), latency_s=0.001)


def make_client(settings: Settings):
    if settings.provider == "ollama":
        return OllamaClient(settings.model, settings.base_url)
    if settings.provider == "ollama_cloud":
        if not settings.api_key:
            raise LLMError("no API key for provider 'ollama_cloud' (set OLLAMA_API_KEY)")
        return OllamaClient(settings.model, settings.base_url, api_key=settings.api_key, think=None)
    if settings.provider in ("groq", "openai"):
        if not settings.api_key:
            raise LLMError(f"no API key for provider '{settings.provider}' (set NATURALSQL_API_KEY or GROQ_API_KEY/OPENAI_API_KEY)")
        return OpenAICompatClient(settings.base_url, settings.api_key, settings.model, name=f"{settings.provider}:{settings.model}")
    if settings.provider == "custom":
        return OpenAICompatClient(settings.base_url, settings.api_key, settings.model)
    raise LLMError(f"unknown provider '{settings.provider}'")
