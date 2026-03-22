"""OpenAI provider adapter."""
from __future__ import annotations

from app.providers.base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, api_key: str, base_url: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("Install 'openai' package: pip install openai") from e
        self._client = OpenAI(api_key=api_key, base_url=base_url or None)

    def send(self, messages: list[dict[str, str]], model: str, **kwargs) -> str:
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    def healthcheck(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False
