"""Anthropic provider adapter."""
from __future__ import annotations

import anthropic
from app.providers.base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def send(self, messages: list[dict[str, str]], model: str, **kwargs) -> str:
        # Anthropic's API separates system messages from the conversation turns
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        chat_messages = [m for m in messages if m["role"] != "system"]

        system_text = "\n".join(system_parts)

        resp = self._client.messages.create(
            model=model,
            max_tokens=kwargs.pop("max_tokens", 4096),
            system=system_text or anthropic.NOT_GIVEN,
            messages=chat_messages,  # type: ignore[arg-type]
            **kwargs,
        )
        return resp.content[0].text if resp.content else ""

    def healthcheck(self) -> bool:
        try:
            # Lightweight call to validate credentials
            self._client.models.list()
            return True
        except Exception:
            return False
