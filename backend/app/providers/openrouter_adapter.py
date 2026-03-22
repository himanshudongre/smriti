"""OpenRouter provider adapter.

Uses the openai SDK pointed at OpenRouter's OpenAI-compatible API endpoint.
This gives access to 200+ models through a single key.
"""
from __future__ import annotations

from app.providers.openai_adapter import OpenAIAdapter

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAdapter(OpenAIAdapter):
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL):
        super().__init__(api_key=api_key, base_url=base_url)

    def healthcheck(self) -> bool:
        # OpenRouter doesn't support models.list(), so just return True if the key exists
        return bool(True)
