"""Embedding service for semantic vectors."""

import random
from typing import Protocol

from openai import AsyncOpenAI


class EmbeddingService(Protocol):
    """Protocol for embedding generation."""

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a vector embedding for the given text."""
        ...


class OpenAIEmbeddingService:
    """Uses OpenAI's text-embedding-3-small to generate embeddings."""

    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_embedding(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * 1536

        # Standard OpenAI embedding dimension for text-embedding-3-small is 1536
        response = await self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
        )
        return response.data[0].embedding


class MockEmbeddingService:
    """Mock service for testing/local dev without an API key."""

    async def generate_embedding(self, text: str) -> list[float]:
        # Return a normalized random vector of size 1536
        if not text or not text.strip():
            return [0.0] * 1536

        vec = [random.uniform(-1.0, 1.0) for _ in range(1536)]
        magnitude = sum(x * x for x in vec) ** 0.5
        if magnitude == 0:
            return vec
        return [x / magnitude for x in vec]
