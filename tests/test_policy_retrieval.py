"""Testes da busca no manual de políticas (sem chamadas de rede)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from emporio.business_hours import STORE_TZ
from emporio.rag.bm25 import BM25
from emporio.rag.embeddings import CachedEmbedder
from emporio.rag.evaluate import DATASET, HOLDOUT, evaluate, load_dataset
from emporio.rag.retriever import PolicyRetriever, load_chunks
from emporio.rag.text import tokenize, tokenize_query
from emporio.repository import StoreRepository
from emporio.tools import ToolContext, build_tools
from emporio.tools.policies import SearchPoliciesInput, search_policies


class FakeEmbedder:
    """Bag-of-words com hashing: determinístico e offline, só para testar o encanamento."""

    model = "fake-embedding"

    def __init__(self, dims: int = 128, fail: bool = False) -> None:
        self.dims, self.fail, self.calls = dims, fail, 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("provedor fora do ar")
        vectors = []
        for text in texts:
            v = [0.0] * self.dims
            for token in tokenize(text):
                v[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0
            vectors.append(v)
        return vectors


@pytest.fixture(scope="module")
def sections_path(database_path: Path) -> Path:
    return database_path.parent / "policy_sections.json"


@pytest.fixture(scope="module")
def chunks(sections_path: Path):
    return load_chunks(sections_path)


@pytest.fixture(scope="module")
def bm25(chunks) -> PolicyRetriever:
    return PolicyRetriever(chunks, mode="bm25")


# --- Pré-processamento -----------------------------------------------------------


def test_tokenize_normalizes_and_stems() -> None:
    assert tokenize("Devoluções") == tokenize("devolucao")
    assert "voce" not in tokenize("você pode")  # stopwords removidas


def test_query_expansion() -> None:
    assert set(tokenize("arrependimento")) <= set(tokenize_query("quero devolver"))
    assert set(tokenize("devolucao")) <= set(tokenize_query("posso mandar de volta?"))


def test_bm25_ranks_exact_term_first() -> None:
    index = BM25([["pix", "desconto"], ["frete", "gratis"], ["pix", "pix", "pagamento"]])
    scores = index.scores(["frete"])
    assert scores.index(max(scores)) == 1
    assert index.scores(["inexistente"]) == [0.0, 0.0, 0.0]


# --- Chunks ----------------------------------------------------------------------


def test_one_chunk_per_section_with_text(chunks) -> None:
    ids = [c.section_id for c in chunks]
    assert len(chunks) == 26
    assert "5" not in ids and "6" not in ids and "8" not in ids  # só título, sem texto
    by_id = {c.section_id: c for c in chunks}
    assert by_id["5.1"].parent_title == "Política de Frete e Entregas"
    assert by_id["5.1"].heading.startswith("Política de Frete e Entregas › 5.1.")


# --- Recuperação -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "sections"),
    [
        ("Qual o CNPJ?", {"1.2"}),
        ("Posso trocar a boquilha?", {"4.4"}),
        ("Trabalham com a Jadlog?", {"5.2", "5.3"}),  # o termo aparece nas duas seções
    ],
)
def test_bm25_exact_terms(bm25: PolicyRetriever, query: str, sections: set[str]) -> None:
    assert bm25.search(query, k=1)[0].chunk.section_id in sections


def test_bm25_regression_on_dev_set(bm25: PolicyRetriever) -> None:
    """Guarda contra regressões. O dev set foi usado para ajustar as expansões; a medida
    honesta de generalização é o holdout (ver README)."""
    assert evaluate(bm25, load_dataset(DATASET)).hit_at_3 >= 0.95


def test_holdout_is_disjoint_from_dev() -> None:
    dev = {c.question for c in load_dataset(DATASET)}
    holdout = {c.question for c in load_dataset(HOLDOUT)}
    assert dev.isdisjoint(holdout) and len(holdout) >= 20


def test_hybrid_fuses_both_rankings(chunks) -> None:
    retriever = PolicyRetriever(chunks, FakeEmbedder(), mode="hybrid")
    hits = retriever.search("Qual o CNPJ da empresa?", k=3)
    assert hits[0].chunk.section_id == "1.2"
    assert set(hits[0].matched_by) == {"bm25", "embeddings"}
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_chunk_vectors_are_computed_once(chunks) -> None:
    embedder = FakeEmbedder()
    retriever = PolicyRetriever(chunks, embedder, mode="embeddings")
    retriever.search("pix")
    retriever.search("frete")
    assert embedder.calls == 3  # 1x as seções + 1x por consulta


def test_falls_back_to_bm25_when_embeddings_fail(chunks) -> None:
    retriever = PolicyRetriever(chunks, FakeEmbedder(fail=True), mode="embeddings")
    hits = retriever.search("Qual o CNPJ?")
    assert retriever.degraded
    assert hits and hits[0].chunk.section_id == "1.2"
    assert hits[0].matched_by == ("bm25",)


def test_without_embedder_uses_bm25(chunks) -> None:
    assert PolicyRetriever(chunks, None, mode="hybrid").mode == "bm25"


def test_cached_embedder_persists(tmp_path: Path) -> None:
    cache = tmp_path / "emb.json"
    inner = FakeEmbedder()
    first = CachedEmbedder(inner, cache)
    first.embed(["a", "b"])
    first.embed(["a", "c"])  # só "c" é novo
    assert inner.calls == 2
    assert len(json.loads(cache.read_text())) == 3

    reloaded_inner = FakeEmbedder()
    CachedEmbedder(reloaded_inner, cache).embed(["a", "b", "c"])
    assert reloaded_inner.calls == 0


# --- Ferramenta search_policies ---------------------------------------------------


@pytest.fixture
def ctx(repo: StoreRepository, bm25: PolicyRetriever) -> ToolContext:
    now = datetime(2026, 3, 2, 10, 30, tzinfo=STORE_TZ)
    return ToolContext(repo=repo, clock=lambda: now, policies=bm25)


def test_search_policies_attaches_official_interpretation(ctx: ToolContext) -> None:
    result = search_policies(ctx, SearchPoliciesInput(query="Qual o número do WhatsApp?"))
    assert result.excerpts[0].section in {"7", "1.2", "0"}
    assert any("(67) 3341-4444" in i for i in result.official_interpretations)


def test_search_policies_without_interpretation(ctx: ToolContext) -> None:
    result = search_policies(ctx, SearchPoliciesInput(query="O que fazem com meus dados pessoais? LGPD"))
    assert result.excerpts[0].section == "9"
    assert result.official_interpretations == []


def test_search_policies_registered(ctx: ToolContext) -> None:
    tools = {t.name: t for t in build_tools(ctx)}
    payload = json.loads(tools["search_policies"].invoke({"query": "aceitam boleto?"}))
    assert payload["excerpts"] and "notes" in payload


def test_search_policies_without_retriever(repo: StoreRepository) -> None:
    ctx = ToolContext(repo=repo, clock=lambda: datetime.now(STORE_TZ))
    tools = {t.name: t for t in build_tools(ctx)}
    assert "indisponível" in tools["search_policies"].invoke({"query": "aceitam boleto?"})
