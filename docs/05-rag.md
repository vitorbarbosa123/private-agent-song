# Busca no manual de políticas (RAG)

[← Voltar ao README](../README.md)

Implementada em [`src/emporio/rag/`](../src/emporio/rag/) e exposta ao agente pela ferramenta
`search_policies`.

**Chunking.** Cada seção numerada do manual vira um chunk, e o título da seção-mãe é incorporado
("Política de Frete e Entregas › 5.1. Entregas na Região Metropolitana…"). As seções têm no máximo
~800 caracteres e tratam de um único assunto, então o corte natural do documento é melhor que
janelas de tamanho fixo. Isso também permite citar a seção na resposta. São 26 chunks; seções que
têm só título são omitidas.

**Interpretações oficiais junto dos trechos.** Quando a seção mais relevante tem uma contradição
resolvida em `policy_rules.RESOLUTIONS`, a ferramenta devolve a decisão junto com o texto. Exemplo:
a seção 7 cita o WhatsApp (67) 3321-4500, e a resposta acrescenta "número canônico:
(67) 3341-4444". Assim o modelo não repete uma contradição do manual.

**Avaliação e escolha da estratégia.** Montei dois conjuntos de perguntas de clientes, cada uma com
as seções esperadas:

- [`evals/policy_retrieval.json`](../evals/policy_retrieval.json) (**dev**, 28 perguntas): usado
  para ajustar a busca.
- [`evals/policy_retrieval_holdout.json`](../evals/policy_retrieval_holdout.json) (**holdout**, 22
  paráfrases novas): escrito antes de qualquer medição nele e nunca usado para ajustes.

Comparação de modelos de embedding (dev, busca só por embeddings):

| Modelo | hit@1 | hit@3 | MRR |
|---|---:|---:|---:|
| `openai/text-embedding-3-small` | 75% | 96% | 0,85 |
| `openai/text-embedding-3-large` | 71% | 93% | 0,82 |
| `qwen/qwen3-embedding-8b` | 61% | 93% | 0,77 |
| **`google/gemini-embedding-001`** | **82%** | **96%** | **0,89** |

Comparação de estratégias com `gemini-embedding-001`:

| Modo | dev hit@1 | dev hit@3 | **holdout hit@1** | **holdout hit@3** | holdout MRR |
|---|---:|---:|---:|---:|---:|
| BM25 (+ stemming e sinônimos) | 86% | 100% | 73% | 82% | 0,77 |
| **Embeddings** | 82% | 96% | **95%** | **100%** | **0,98** |
| Híbrido (Reciprocal Rank Fusion) | 86% | 100% | 86% | 91% | 0,89 |

**O que os números mostraram.** O BM25 parecia o melhor no dev, mas eu tinha ajustado os
sinônimos dele olhando os erros desse mesmo conjunto. No holdout ele cai para 82% de hit@3: não
generaliza para paráfrases novas ("até que horas ficam abertos?", "o captador parou de
funcionar"). A minha hipótese inicial, de que o híbrido seria o melhor, também não se confirmou:
com pesos iguais no RRF, o BM25 puxa o resultado para baixo. Por isso:

- o **padrão é busca só por embeddings** (`RETRIEVAL_MODE=embeddings`);
- o **BM25 é o fallback automático**: se a API de embeddings falhar, a busca degrada em vez de
  falhar, e o agente é avisado;
- o modo híbrido continua disponível por configuração, mas não calibrei os pesos do RRF no
  holdout, para não contaminá-lo.

**Custo e latência.** Os vetores das 26 seções são calculados uma vez e guardados em cache
(`data/processed/policy_embeddings.json`, indexado por modelo + hash do texto). Cada pergunta do
cliente gera uma chamada de embedding, de custo desprezível (~US$ 0,000001).
