"""LLM provider interface and base classes."""

from typing import Protocol

from app.domain.models import ExtractionResult, Message


class LLMProvider(Protocol):
    """Interface for LLM providers used in extraction."""

    async def extract(self, messages: list[Message]) -> ExtractionResult:
        """Extract structured artifacts from a list of messages.

        Args:
            messages: Parsed messages from a transcript.

        Returns:
            ExtractionResult with summary, decisions, tasks, etc.
        """
        ...

    async def extract_memories(self, messages: list[Message]) -> list['app.domain.models.ExtractedMemory']:
        """Extract generic memory items from a list of messages.
        
        Args:
            messages: Parsed messages from a transcript.
            
        Returns:
            List of generic extracted memories.
        """
        ...
