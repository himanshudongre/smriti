"""Provider registry — resolves provider name → adapter instance."""
from __future__ import annotations

import json as _json

from app.config_loader import get_provider_config, ProviderNotConfiguredError
from app.providers.base import ProviderAdapter


# Canned JSON response returned by the mock adapter when the caller asks
# for JSON mode (response_format={"type": "json_object"}). Covers every
# field any current Smriti LLM-backed endpoint looks for: draft, review,
# extract. Tests can assert on specific values because the response is
# deterministic.
_MOCK_JSON_RESPONSE = {
    "title": "Mock Checkpoint",
    "objective": "Mock objective from the deterministic provider.",
    "summary": "Mock summary produced by MockAdapter for deterministic testing.",
    "decisions": ["Mock decision from provider"],
    "assumptions": ["Mock assumption from provider"],
    "tasks": ["Mock task from provider"],
    "open_questions": ["Mock open question from provider"],
    "entities": ["MockEntity"],
    "artifacts": [
        {
            "id": "mock-a1",
            "type": "text",
            "label": "Mock artifact",
            "content": "Mock artifact content from deterministic provider.",
        }
    ],
    "issues": [],
    "suggestions": [],
}


class MockAdapter(ProviderAdapter):
    """Deterministic mock adapter used in tests and when no real keys are present."""

    def send(self, messages: list[dict[str, str]], model: str, **kwargs) -> str:
        # JSON mode: callers (draft, review, extract) that ask for structured
        # output via response_format={"type": "json_object"} get a canned
        # valid JSON blob covering every common Smriti schema field. This is
        # what makes LLM-backed endpoint tests pass without real provider keys.
        response_format = kwargs.get("response_format") or {}
        if isinstance(response_format, dict) and response_format.get("type") == "json_object":
            return _json.dumps(_MOCK_JSON_RESPONSE)

        # Text mode (chat.send path): echo the user's last message.
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "Hello",
        )
        return (
            f"[mock:{model}] You said: \"{last_user[:80]}\". "
            "This is a deterministic mock response from Smriti's provider layer. "
            "Configure a real provider key to use a live model."
        )

    def healthcheck(self) -> bool:
        return True


def get_adapter(provider: str, allow_mock: bool = False) -> ProviderAdapter:
    """
    Return the adapter for the given provider name.

    If allow_mock=True and the provider has no key, returns MockAdapter instead
    of raising an error. Useful for demos and tests.
    """
    p = provider.lower()

    try:
        cfg = get_provider_config(p)
    except ProviderNotConfiguredError:
        if allow_mock:
            return MockAdapter()
        raise

    if p == "openai":
        try:
            from app.providers.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=cfg.api_key)
        except ImportError as e:
            raise ProviderNotConfiguredError(str(e))

    if p == "anthropic":
        try:
            from app.providers.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(api_key=cfg.api_key)
        except ImportError as e:
            raise ProviderNotConfiguredError(str(e))

    if p == "openrouter":
        try:
            from app.providers.openrouter_adapter import OpenRouterAdapter
            return OpenRouterAdapter(api_key=cfg.api_key, base_url=cfg.base_url or "https://openrouter.ai/api/v1")
        except ImportError as e:
            raise ProviderNotConfiguredError(str(e))

    raise ProviderNotConfiguredError(f"Unknown provider: {provider}")


def get_mock_adapter() -> MockAdapter:
    """Always return a mock adapter, for tests and offline demos."""
    return MockAdapter()
