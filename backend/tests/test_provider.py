"""LLM provider layer: presets (incl. GLM coding-plan endpoints) and base-URL
resolution rules."""
import pytest

from services.llm.provider import PROVIDER_PRESETS, LLMError, resolve_base_url


class TestPresets:
    def test_kimi_coding_endpoint(self):
        assert resolve_base_url('kimi_coding', None) == 'https://api.kimi.ai/coding/v1'
        assert PROVIDER_PRESETS['kimi_coding']['example_model'] == 'k3.1-pro'

    def test_zhipu_global_is_z_ai_coding_endpoint(self):
        p = PROVIDER_PRESETS["zhipu_global"]
        assert p["base_url"] == "https://api.z.ai/api/coding/paas/v4"
        assert p["supports_tools"]

    def test_zhipu_coding_cn(self):
        assert PROVIDER_PRESETS["zhipu_coding"]["base_url"] \
            == "https://open.bigmodel.cn/api/coding/paas/v4"

    def test_every_preset_has_required_fields(self):
        for key, p in PROVIDER_PRESETS.items():
            assert p["label"], key
            assert "supports_tools" in p, key
            assert "example_model" in p, key


class TestResolveBaseUrl:
    def test_override_wins_and_trims_slash(self):
        assert resolve_base_url("zhipu_global", "https://x.example/v1//") == "https://x.example/v1"

    def test_preset_used_without_override(self):
        assert resolve_base_url("openai", None) == "https://api.openai.com/v1"

    def test_custom_without_override_raises(self):
        with pytest.raises(LLMError):
            resolve_base_url("custom", None)

    def test_unknown_provider_without_override_raises(self):
        with pytest.raises(LLMError):
            resolve_base_url("nonexistent", None)


class TestChatRetries:
    """Transient transport failures (DNS hiccups, conn resets, provider 503/
    429) must be retried with backoff — one blip must not kill an agent run
    (regression: task failed live with [Errno -5] on a single DNS miss)."""

    @staticmethod
    def _client():
        from services.llm.provider import LLMClient
        return LLMClient(base_url="http://fake.local/v1", api_key="k",
                         model="fake-1", provider="custom")

    async def test_transient_dns_error_then_success(self, monkeypatch):
        import httpx
        import services.llm.provider as prov
        c = self._client()
        sleeps = []
        monkeypatch.setattr(prov.asyncio, "sleep", lambda s: sleeps.append(s) or _noop())

        attempts = {"n": 0}

        async def fake_post(self, url, **kw):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise httpx.ConnectError("[Errno -5] No address associated with hostname")
            return _ok_response()

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        out = await c.chat([{"role": "user", "content": "x"}])
        assert out["content"] == "hi"
        assert attempts["n"] == 2            # one retry, then success
        assert sleeps == [1.5]               # backoff ran

    async def test_all_attempts_exhausted_raises_llm_error(self, monkeypatch):
        import httpx
        import services.llm.provider as prov
        c = self._client()
        monkeypatch.setattr(prov.asyncio, "sleep", lambda s: _noop())

        async def fake_post(self, url, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        with pytest.raises(Exception) as ei:
            await c.chat([{"role": "user", "content": "x"}])
        assert "after 3 retries" in str(ei.value)

    async def test_500_retried_then_success(self, monkeypatch):
        import httpx
        import services.llm.provider as prov
        c = self._client()
        monkeypatch.setattr(prov.asyncio, "sleep", lambda s: _noop())
        attempts = {"n": 0}

        async def fake_post(self, url, **kw):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                return httpx.Response(503, request=httpx.Request("POST", "http://x"),
                                      text="upstream down")
            return _ok_response()

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        out = await c.chat([{"role": "user", "content": "x"}])
        assert out["content"] == "hi"
        assert attempts["n"] == 3

    async def test_400_fails_fast_no_retry(self, monkeypatch):
        import httpx
        c = self._client()
        attempts = {"n": 0}

        async def fake_post(self, url, **kw):
            attempts["n"] += 1
            return httpx.Response(401, request=httpx.Request("POST", "http://x"),
                                  text="bad key")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        from services.llm.provider import LLMError
        with pytest.raises(LLMError):
            await c.chat([{"role": "user", "content": "x"}])
        assert attempts["n"] == 1            # auth errors are not retried


async def _noop():
    return None


def _ok_response():
    import httpx
    return httpx.Response(200, request=httpx.Request("POST", "http://x"),
                          json={"choices": [{"message": {"content": "hi"}}],
                                "usage": {}})
