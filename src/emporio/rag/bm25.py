"""BM25 Okapi (implementação própria, ~30 linhas, sem dependências).

Para um corpus de ~30 seções, uma implementação direta é mais transparente do que
adicionar uma biblioteca.
"""

from __future__ import annotations

import math
from collections import Counter


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_freqs = [Counter(doc) for doc in corpus]
        self.doc_lens = [len(doc) for doc in corpus]
        self.avg_len = sum(self.doc_lens) / len(corpus) if corpus else 0.0
        n_docs = len(corpus)
        df = Counter(term for doc in corpus for term in set(doc))
        # IDF com suavização (+1) para nunca ficar negativo em termos muito frequentes.
        self.idf = {t: math.log(1 + (n_docs - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        results = []
        for freqs, length in zip(self.doc_freqs, self.doc_lens, strict=True):
            score = 0.0
            for term in query:
                tf = freqs.get(term, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                    score += self.idf[term] * tf * (self.k1 + 1) / norm
            results.append(score)
        return results
