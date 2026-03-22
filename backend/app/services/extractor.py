"""Extraction service — orchestrates LLM-based context extraction."""

from app.domain.models import ExtractionResult, Message
from app.services.llm.base import LLMProvider


class ExtractorService:
    """Extracts structured artifacts from parsed messages using an LLM provider.

    The LLM provider is injected, enabling:
    - MockProvider for tests (deterministic, no API calls)
    - OpenAIProvider for production
    """

    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider

    async def extract(self, messages: list[Message]) -> ExtractionResult:
        """Extract structured artifacts from parsed messages.

        Args:
            messages: List of parsed Message objects from a transcript.

        Returns:
            ExtractionResult containing summary, decisions, tasks, etc.
        """
        result = await self.llm_provider.extract(messages)
        return result

    async def extract_memories(self, messages: list[Message]) -> list['app.domain.models.ExtractedMemory']:
        """Extract generic memory items from parsed messages.

        Args:
            messages: List of parsed Message objects.

        Returns:
            List of ExtractedMemory objects.
        """
        return await self.llm_provider.extract_memories(messages)
