# Policy retrieval (RAG)

[← Back to README](../README.md)

Implemented in [`src/emporio/rag/`](../src/emporio/rag/) and exposed to the agent through the
`search_policies` tool.

**Chunking.** Each numbered section of the manual becomes one chunk, with the parent section's
title included ("Política de Frete e Entregas › 5.1. Entregas na Região Metropolitana…"). Sections
have at most ~800 characters and cover a single topic, so the document's natural structure works
better than fixed-size windows. It also lets the agent cite the section. There are 26 chunks;
sections that only have a heading are skipped.

**Official interpretations alongside the excerpts.** When the most relevant section has a
contradiction resolved in `policy_rules.RESOLUTIONS`, the tool returns the decision together with
the text. Example: section 7 mentions the WhatsApp number (67) 3321-4500, and the result adds
"canonical number: (67) 3341-4444". This way the model does not repeat a contradiction from the
manual.

**Evaluation and choice of strategy.** I built two sets of customer questions, each with the
expected sections:

- [`evals/policy_retrieval.json`](../evals/policy_retrieval.json) (**dev**, 28 questions): used
  to tune retrieval.
- [`evals/policy_retrieval_holdout.json`](../evals/policy_retrieval_holdout.json) (**holdout**, 22
  new paraphrases): written before any measurement on it and never used for tuning.

Embedding model comparison (dev, embeddings-only retrieval):

| Model | hit@1 | hit@3 | MRR |
|---|---:|---:|---:|
| `openai/text-embedding-3-small` | 75% | 96% | 0.85 |
| `openai/text-embedding-3-large` | 71% | 93% | 0.82 |
| `qwen/qwen3-embedding-8b` | 61% | 93% | 0.77 |
| **`google/gemini-embedding-001`** | **82%** | **96%** | **0.89** |

Strategy comparison with `gemini-embedding-001`:

| Mode | dev hit@1 | dev hit@3 | **holdout hit@1** | **holdout hit@3** | holdout MRR |
|---|---:|---:|---:|---:|---:|
| BM25 (+ stemming and synonyms) | 86% | 100% | 73% | 82% | 0.77 |
| **Embeddings** | 82% | 96% | **95%** | **100%** | **0.98** |
| Hybrid (Reciprocal Rank Fusion) | 86% | 100% | 86% | 91% | 0.89 |

**What the numbers showed.** BM25 looked best on dev, but I had tuned its synonyms by looking at
the errors on that same set. On the holdout it drops to 82% hit@3: it does not generalize to new
paraphrases ("até que horas ficam abertos?", "o captador parou de funcionar"). My initial
hypothesis, that hybrid would be best, did not hold either: with equal RRF weights, BM25 drags the
result down. Therefore:

- **embeddings-only retrieval is the default** (`RETRIEVAL_MODE=embeddings`);
- **BM25 is the automatic fallback**: if the embeddings API fails, retrieval degrades instead of
  failing, and the agent is told;
- hybrid mode remains available by configuration, but I did not tune the RRF weights on the
  holdout, so as not to contaminate it.

**Cost and latency.** The vectors for the 26 sections are computed once and cached
(`data/processed/policy_embeddings.json`, keyed by model + text hash). Each customer question
triggers one embedding call, at negligible cost (~US$ 0.000001).
