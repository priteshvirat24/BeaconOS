"""Beacon Command — Embedding Provider.

Provides vector embeddings for semantic search across evidence and memory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from beacon.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector dimensions."""
        ...


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embedding provider."""

    def __init__(self, api_key: str, model: str = "text-embedding-004", dims: int = 768):
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @property
    def dimensions(self) -> int:
        return self._dims

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        result = client.models.embed_content(
            model=self._model,
            contents=texts,
        )
        return [e.values for e in result.embeddings]

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dims: int = 768):
        self._api_key = api_key
        self._model = model
        self._dims = dims
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    @property
    def dimensions(self) -> int:
        return self._dims

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embeddings.create(model=self._model, input=texts)
        return [e.embedding[:self._dims] for e in response.data]

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]


def create_embedding_provider(settings: Any) -> EmbeddingProvider:
    """Factory to create the configured embedding provider."""
    from beacon.config import EmbeddingProviderType

    if settings.embedding_provider == EmbeddingProviderType.GEMINI:
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.embedding_model,
            dims=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == EmbeddingProviderType.OPENAI:
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dims=settings.embedding_dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
