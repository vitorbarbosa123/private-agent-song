"""Avalia a busca no manual com perguntas de clientes e as seções esperadas.

Uso:
    uv run emporio-eval-retrieval                       # compara bm25, embeddings e híbrido
    uv run emporio-eval-retrieval --embedding-model qwen/qwen3-embedding-8b
    uv run emporio-eval-retrieval --dataset holdout     # conjunto de validação

Métricas:
    hit@1 / hit@3: fração de perguntas com uma seção esperada no 1º / entre os 3 primeiros
    MRR:           média de 1/posição da primeira seção esperada (0 se fora do top-k)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from emporio.config import Settings, get_settings
from emporio.data.paths import PROJECT_ROOT
from emporio.rag.embeddings import CachedEmbedder, OpenAICompatibleEmbedder
from emporio.rag.retriever import PolicyRetriever, load_chunks

DATASET = PROJECT_ROOT / "evals" / "policy_retrieval.json"
# Validação: paráfrases escritas antes de qualquer ajuste e nunca usadas para calibrar a busca.
HOLDOUT = PROJECT_ROOT / "evals" / "policy_retrieval_holdout.json"


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected: frozenset[str]


@dataclass(frozen=True)
class EvalResult:
    hit_at_1: float
    hit_at_3: float
    mrr: float
    misses: list[tuple[str, list[str]]]


def load_dataset(path: Path = DATASET) -> list[EvalCase]:
    return [EvalCase(c["question"], frozenset(c["expected"])) for c in json.loads(path.read_text(encoding="utf-8"))]


def evaluate(retriever: PolicyRetriever, cases: list[EvalCase], k: int = 3) -> EvalResult:
    hits1 = hits3 = 0
    rr = 0.0
    misses = []
    for case in cases:
        ids = [h.chunk.section_id for h in retriever.search(case.question, k=k)]
        rank = next((i for i, sid in enumerate(ids, start=1) if sid in case.expected), None)
        hits1 += rank == 1
        hits3 += rank is not None and rank <= 3
        rr += 1 / rank if rank else 0.0
        if rank is None:
            misses.append((case.question, ids))
    n = len(cases)
    return EvalResult(hits1 / n, hits3 / n, rr / n, misses)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding-model", help="Sobrescreve EMBEDDING_MODEL.")
    parser.add_argument("--modes", default="bm25,embeddings,hybrid")
    parser.add_argument("--dataset", choices=["dev", "holdout"], default="dev",
                        help="dev: usado para ajustes; holdout: só para medir.")
    args = parser.parse_args(argv)

    settings: Settings = get_settings()
    if args.embedding_model:
        settings = settings.model_copy(update={"embedding_model": args.embedding_model})
    sections = settings.database_path.parent / "policy_sections.json"
    chunks = load_chunks(sections)
    cases = load_dataset(HOLDOUT if args.dataset == "holdout" else DATASET)
    embedder = None
    if settings.embedding_model and settings.llm_api_key:
        embedder = CachedEmbedder(OpenAICompatibleEmbedder(settings), sections.parent / "policy_embeddings.json")

    model_name = settings.embedding_model or "-"
    print(f"[{args.dataset}] {len(cases)} perguntas · {len(chunks)} seções · embeddings: {model_name}\n")
    print(f"{'modo':<12}{'hit@1':>8}{'hit@3':>8}{'MRR':>8}")
    all_misses = {}
    for mode in args.modes.split(","):
        mode = mode.strip()
        if mode != "bm25" and embedder is None:
            print(f"{mode:<12}  (sem embeddings configurados)")
            continue
        result = evaluate(PolicyRetriever(chunks, embedder, mode=mode), cases)  # type: ignore[arg-type]
        print(f"{mode:<12}{result.hit_at_1:>8.0%}{result.hit_at_3:>8.0%}{result.mrr:>8.2f}")
        all_misses[mode] = result.misses
    for mode, misses in all_misses.items():
        for question, got in misses:
            print(f"\n[{mode}] errou: {question!r} -> {got}")


if __name__ == "__main__":
    main()
