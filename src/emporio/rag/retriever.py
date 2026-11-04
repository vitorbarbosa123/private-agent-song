"""Busca no manual de políticas: BM25 + embeddings, combinados por Reciprocal Rank Fusion.

Por que híbrido:
- BM25 acerta termos exatos do manual ("PIX", "boquilha", "CNPJ", "Jadlog");
- embeddings acertam paráfrases ("posso mandar de volta?" -> direito de arrependimento);
- RRF combina os dois rankings sem precisar calibrar escalas de score diferentes.

Se os embeddings falharem (sem chave, rede, provedor fora), a busca degrada para BM25
em vez de falhar: o agente continua respondendo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from emporio.rag.bm25 import BM25
from emporio.rag.embeddings import CachedEmbedder, Embedder, cosine
from emporio.rag.text import tokenize, tokenize_query

logger = logging.getLogger(__name__)

Mode = Literal["hybrid", "bm25", "embeddings"]
RRF_K = 60  # constante usual do RRF (Cormack et al., 2009)


@dataclass(frozen=True)
class PolicyChunk:
    section_id: str
    title: str
    parent_title: str | None
    text: str

    @property
    def heading(self) -> str:
        prefix = "" if self.section_id == "0" else f"{self.section_id}. "
        parent = f"{self.parent_title} › " if self.parent_title else ""
        return f"{parent}{prefix}{self.title}"

    @property
    def search_text(self) -> str:
        return f"{self.heading}\n{self.text}"


@dataclass(frozen=True)
class PolicyHit:
    chunk: PolicyChunk
    score: float
    matched_by: tuple[str, ...]


def load_chunks(sections_path: Path) -> list[PolicyChunk]:
    """Uma seção do manual = um chunk. Seções só com título (ex.: '5. Frete') são omitidas;
    o título do pai é incorporado ao chunk filho."""
    sections = json.loads(sections_path.read_text(encoding="utf-8"))
    titles = {s["section_id"]: s["title"] for s in sections}
    chunks = []
    for s in sections:
        if not s["text"]:
            continue
        title = "Capa (endereço e contatos)" if s["section_id"] == "0" else s["title"]
        chunks.append(PolicyChunk(s["section_id"], title, titles.get(s["parent_id"]), s["text"]))
    return chunks


class PolicyRetriever:
    def __init__(self, chunks: list[PolicyChunk], embedder: Embedder | None = None, mode: Mode = "hybrid") -> None:
        if mode != "bm25" and embedder is None:
            logger.warning("Embeddings não configurados; usando apenas BM25.")
            mode = "bm25"
        self.chunks = chunks
        self.mode: Mode = mode
        self.embedder = embedder
        self._bm25 = BM25([tokenize(c.search_text) for c in chunks])
        self._chunk_vectors: list[list[float]] | None = None
        self.degraded = False  # True se a última busca caiu para BM25 por erro nos embeddings

    @classmethod
    def from_settings(cls, settings, sections_path: Path | None = None) -> PolicyRetriever:  # noqa: ANN001
        from emporio.rag.embeddings import OpenAICompatibleEmbedder

        path = sections_path or settings.database_path.parent / "policy_sections.json"
        embedder: Embedder | None = None
        if settings.embedding_model and settings.retrieval_mode != "bm25":
            try:
                embedder = CachedEmbedder(
                    OpenAICompatibleEmbedder(settings), path.parent / "policy_embeddings.json"
                )
            except ValueError as exc:
                logger.warning("%s", exc)
        return cls(load_chunks(path), embedder, settings.retrieval_mode)

    # --- rankings individuais ------------------------------------------------

    def _bm25_ranking(self, query: str) -> list[int]:
        scores = self._bm25.scores(tokenize_query(query))
        return [i for i in sorted(range(len(scores)), key=lambda i: -scores[i]) if scores[i] > 0]

    def _embedding_ranking(self, query: str) -> list[int]:
        assert self.embedder is not None
        if self._chunk_vectors is None:
            self._chunk_vectors = self.embedder.embed([c.search_text for c in self.chunks])
        query_vector = self.embedder.embed([query])[0]
        sims = [cosine(query_vector, v) for v in self._chunk_vectors]
        return sorted(range(len(sims)), key=lambda i: -sims[i])

    # --- busca ---------------------------------------------------------------

    def search(self, query: str, k: int = 3) -> list[PolicyHit]:
        rankings: dict[str, list[int]] = {}
        if self.mode in {"bm25", "hybrid"}:
            rankings["bm25"] = self._bm25_ranking(query)
        self.degraded = False
        if self.mode in {"embeddings", "hybrid"}:
            try:
                rankings["embeddings"] = self._embedding_ranking(query)
            except Exception as exc:  # noqa: BLE001 — degrada para BM25 em qualquer falha de rede/API
                logger.warning("Busca semântica indisponível (%s); usando BM25.", exc)
                self.degraded = True
                rankings.setdefault("bm25", self._bm25_ranking(query))

        fused: dict[int, float] = {}
        sources: dict[int, list[str]] = {}
        for name, ranking in rankings.items():
            for rank, idx in enumerate(ranking[: max(k * 4, 10)]):
                fused[idx] = fused.get(idx, 0.0) + 1 / (RRF_K + rank + 1)
                sources.setdefault(idx, []).append(name)
        best = sorted(fused, key=lambda i: -fused[i])[:k]
        return [PolicyHit(self.chunks[i], round(fused[i], 5), tuple(sources[i])) for i in best]
