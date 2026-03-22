"""API dependency injection."""

from app.config import settings
from app.services.extractor import ExtractorService
from app.services.llm.mock_provider import MockProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.embedding import EmbeddingService, MockEmbeddingService, OpenAIEmbeddingService


def get_extractor_service() -> ExtractorService:
    """Get the extraction service with the appropriate LLM provider.

    Uses MockProvider if no OpenAI API key is configured,
    otherwise uses OpenAIProvider.
    """
    if settings.openai_api_key:
        provider = OpenAIProvider()
    else:
        provider = MockProvider()
    return ExtractorService(llm_provider=provider)


def get_embedding_service() -> EmbeddingService:
    """Get the embedding service.

    Uses MockEmbeddingService if no OpenAI API key is configured,
    otherwise uses OpenAIEmbeddingService.
    """
    if settings.openai_api_key:
        return OpenAIEmbeddingService(api_key=settings.openai_api_key)
    return MockEmbeddingService()
