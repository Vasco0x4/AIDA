"""
OpenAI-compatible LLM client.

One client covers OpenRouter, Moonshot/Kimi, Zhipu/GLM, OpenAI, DeepSeek, and any
other endpoint that speaks the OpenAI `/chat/completions` schema. Providers that
diverge (e.g. Anthropic's native Messages API) get a dedicated adapter later; for
now Anthropic models are reachable via OpenRouter.

The client is intentionally small and dependency-free (httpx only), returning
plain dicts so callers/agent loops stay simple.
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit
from typing import Any, Optional

import httpx

from utils.logger import get_logger

logger = get_logger(__name__)

# Transient HTTP statuses worth another attempt (timeouts / rate limit /
# provider-side blips). Everything else (400/401/403/404/422…) fails fast —
# retrying an auth or schema error just burns the caller's time.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


# Provider preset → default OpenAI-compatible base URL.
# base_url is always overridable per config row.
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "kimi_coding": {
        "label": "Kimi Code (international)",
        "base_url": "https://api.kimi.ai/coding/v1",
        "example_model": "k3.1-pro",
        "supports_tools": True,
    },
    "openrouter": {
        "label": "OpenRouter (aggregator)",
        "base_url": "https://openrouter.ai/api/v1",
        "example_model": "moonshotai/kimi-k2",
        "supports_tools": True,
    },
    "moonshot": {
        "label": "Moonshot / Kimi (international)",
        "base_url": "https://api.moonshot.ai/v1",
        "example_model": "kimi-k2-0711-preview",
        "supports_tools": True,
    },
    "moonshot_cn": {
        "label": "Moonshot / Kimi (China)",
        "base_url": "https://api.moonshot.cn/v1",
        "example_model": "kimi-k2-0711-preview",
        "supports_tools": True,
    },
    "zhipu": {
        "label": "Zhipu / GLM (China)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "example_model": "glm-5.3",
        "supports_tools": True,
    },
    # GLM Coding Plan keys only work on the /coding/ endpoints (the regular
    # paas endpoint rejects them with 1113 "no resource package").
    "zhipu_coding": {
        "label": "Zhipu / GLM Coding Plan (China)",
        "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
        "example_model": "glm-5.3",
        "supports_tools": True,
    },
    "zhipu_global": {
        "label": "Zhipu / GLM Coding Plan (global, Z.ai)",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "example_model": "glm-5.3",
        "supports_tools": True,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "example_model": "gpt-4o",
        "supports_tools": True,
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "example_model": "deepseek-chat",
        "supports_tools": True,
    },
    "anthropic": {
        # Native Messages API differs from OpenAI; reach Claude via OpenRouter
        # for now. A native adapter is a follow-up (see AUTONOMY_ROADMAP.md).
        "label": "Anthropic (via OpenRouter for now)",
        "base_url": "https://openrouter.ai/api/v1",
        "example_model": "anthropic/claude-sonnet-4",
        "supports_tools": True,
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",
        "example_model": "",
        "supports_tools": True,
    },
}


class LLMError(Exception):
    """Raised on any provider/transport error, with a human-readable message."""


class _TransientStatus(Exception):
    """Retryable HTTP status from the provider (429 / 5xx family)."""

    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status} {body}")
        self.status = status
        self.body = body


def resolve_base_url(provider: str, override: Optional[str]) -> str:
    """Pick the effective base URL: explicit override wins, else preset."""
    if override:
        return override.rstrip("/")
    preset = PROVIDER_PRESETS.get(provider)
    if not preset or not preset["base_url"]:
        raise LLMError(f"No base_url for provider '{provider}'; set one explicitly")
    return preset["base_url"].rstrip("/")


class LLMClient:
    """Minimal OpenAI-compatible chat client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        provider: str = "custom",
        extra_headers: Optional[dict[str, str]] = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter appreciates attribution headers (optional, harmless).
        if self.provider in ("openrouter", "anthropic"):
            headers.setdefault("HTTP-Referer", "https://github.com/Vasco0x4/AIDA")
            headers.setdefault("X-Title", "AIDA")
        headers.update(self.extra_headers)
        return headers

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[Any] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Call /chat/completions. Returns a normalized dict:
        {content, tool_calls, raw, usage, latency_ms}.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
        if extra:
            payload.update(extra)

        # Kimi K3 requires temperature=1 even for callers such as the critic
        # and AppSec that request deterministic output. Detect the actual
        # endpoint too, so existing Custom configurations work unchanged.
        endpoint = urlsplit(self.base_url)
        if (endpoint.hostname in {"api.kimi.ai", "api.kimi.com"}
                and endpoint.path.rstrip('/') == '/coding/v1'
                and self.model.startswith('k3')):
            payload['temperature'] = 1

        url = f"{self.base_url}/chat/completions"
        started = time.monotonic()
        from services.metrics import LLM_CALLS, LLM_ERRORS

        # A single DNS hiccup / conn reset / provider 503 must not kill a
        # 30-minute agent run — retry transient failures with backoff before
        # giving up (observed live: [Errno -5] No address associated with
        # hostname, once, mid-audit).
        retries = 3
        resp = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, headers=self._headers(),
                                             json=payload)
                if resp.status_code in _RETRYABLE_STATUS and attempt < retries:
                    raise _TransientStatus(resp.status_code, resp.text[:300])
                break
            except (httpx.HTTPError, _TransientStatus) as e:
                LLM_ERRORS.labels(provider=self.provider, model=self.model).inc()
                if attempt >= retries:
                    detail = (f"status {e.status}, body={e.body}"
                              if isinstance(e, _TransientStatus) else str(e))
                    raise LLMError(
                        f"Transport error calling {url} "
                        f"(after {retries} retries): {detail}") from e
                delay = 1.5 ** (attempt + 1)          # 1.5s → 2.25s → 3.4s
                logger.warning(
                    "LLM call failed, retrying",
                    provider=self.provider, model=self.model,
                    attempt=attempt + 1, delay=round(delay, 1), error=str(e)[:200])
                await asyncio.sleep(delay)
        latency_ms = int((time.monotonic() - started) * 1000)

        if resp.status_code >= 400:
            detail = resp.text[:500]
            LLM_ERRORS.labels(provider=self.provider, model=self.model).inc()
            raise LLMError(f"{resp.status_code} from provider: {detail}")
        LLM_CALLS.labels(provider=self.provider, model=self.model).inc()

        data = resp.json()
        try:
            choice = data["choices"][0]
            message = choice.get("message", {})
            content = message.get("content")
            tool_calls = message.get("tool_calls")
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected response shape: {e}; body={str(data)[:300]}")

        # E3 accounting: token counters (usage may be absent on some backends).
        try:
            from services.metrics import LLM_TOKENS
            usage = data.get("usage") or {}
            for kind, key in (("prompt", "prompt_tokens"),
                              ("completion", "completion_tokens")):
                n = usage.get(key)
                if isinstance(n, int) and n > 0:
                    LLM_TOKENS.labels(provider=self.provider, model=self.model,
                                      kind=kind).inc(n)
        except Exception:
            pass  # telemetry must never break the call

        return {
            "content": content,
            "reasoning_content": message.get("reasoning_content"),
            "tool_calls": tool_calls,
            "usage": data.get("usage"),
            "raw": data,
            "latency_ms": latency_ms,
        }

    async def test_connection(self, temperature: float = 0.2) -> dict[str, Any]:
        """
        Authoritative auth + model check via a minimal chat completion.

        A short chat is the only universal test that actually validates the
        API key AND the model id AND the endpoint together. (Note: some
        aggregators like OpenRouter expose an UNAUTHENTICATED GET /models, so
        /models is useless for verifying a key — we deliberately don't rely on
        it.) ``temperature`` is honored because some models (e.g. Kimi coding
        K3) reject anything but 1. Returns {ok, message, latency_ms}.
        """
        try:
            # A few reasoning models spend the whole budget on hidden reasoning
            # tokens and return empty text; that's still a successful call, so we
            # give a little headroom rather than max_tokens=1.
            result = await self.chat(
                [{"role": "user", "content": "ping"}], max_tokens=16,
                temperature=temperature,
            )
            return {
                "ok": True,
                "message": f"OK — key + model '{self.model}' valid",
                "latency_ms": result["latency_ms"],
            }
        except LLMError as e:
            msg = str(e)
            # Give a friendlier hint on the common failure modes.
            if msg.startswith("401") or msg.startswith("403"):
                msg = f"Auth rejected — check the API key. ({msg})"
            elif msg.startswith("404"):
                msg = f"Model '{self.model}' not found at this endpoint. ({msg})"
            return {"ok": False, "message": msg, "latency_ms": 0}
