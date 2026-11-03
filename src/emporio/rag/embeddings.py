"""Embeddings via API compatível com a OpenAI (OpenRouter por padrão), com cache em disco.

Os vetores das seções do manual são calculados uma vez e guardados em
`data/processed/policy_embeddings.json`, indexados por modelo + hash do texto. Só a
consulta do cliente gera uma chamada por busca (custo da ordem de US$ 0,0000001).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from emporio.config import Settings

Vector = list[float]


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[Vector]: ...


class OpenAICompatibleEmbedder:
    def __init__(self, settings: Settings) -> None:
        if settings.llm_api_key is None:
            raise ValueError("LLM_API_KEY não configurada; embeddings indisponíveis.")
        self.model = settings.embedding_model
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def embed(self, texts: list[str]) -> list[Vector]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


class CachedEmbedder:
    """Envolve um `Embedder` com cache persistente por (modelo, hash do texto)."""

    def __init__(self, inner: Embedder, cache_path: Path | None) -> None:
        self.inner = inner
        self.model = inner.model
        self.cache_path = cache_path
        self._cache: dict[str, Vector] = {}
        if cache_path and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}\n{text}".encode()).hexdigest()

    def embed(self, texts: list[str]) -> list[Vector]:
        missing = [t for t in dict.fromkeys(texts) if self._key(t) not in self._cache]
        if missing:
            for text, vector in zip(missing, self.inner.embed(missing), strict=True):
                self._cache[self._key(text)] = vector
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        return [self._cache[self._key(t)] for t in texts]


def cosine(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
