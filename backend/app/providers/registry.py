"""Provider registry — resolves provider name → adapter instance."""
from __future__ import annotations

from app.config_loader import get_provider_config, ProviderNotConfiguredError
from app.providers.base import ProviderAdapter


class MockAdapter(ProviderAdapter):
    """Deterministic mock adapter used in tests and when no real keys are present."""

    def send(self, messages: list[dict[str, str]], model: str, **kwargs) -> str:
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
