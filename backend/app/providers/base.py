"""Abstract base for all provider adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderAdapter(ABC):
    """Normalised interface every provider adapter must implement."""

    @abstractmethod
    def send(
        self,
        messages: list[dict[str, str]],
        model: str,
        **kwargs,
    ) -> str:
        """
        Send a list of chat messages and return the assistant reply as a string.

        messages: [{"role": "user"|"assistant"|"system", "content": str}, ...]
        model: provider-specific model slug
        """

    @abstractmethod
    def healthcheck(self) -> bool:
        """Return True if the provider is reachable and configured."""
