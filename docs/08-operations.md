# Operations: observability and CI

[← Back to README](../README.md)

## Observability (Langfuse)

Each customer message becomes a **trace in [Langfuse](https://langfuse.com)**, grouped by
conversation (session). The trace shows the path through the graph: input guardrail, each model
call (with tokens and latency), each tool (with arguments and result) and the final reply. Each
trace also gets **scores** with the indicators the project already measures:

| Score | What it indicates |
|---|---|
| `fallback` | The reply was the error/safety message (provider failure, loop, unverified data) |
| `ferramentas_chamadas` | How many tools were used for the message |
| `correcoes_da_verificacao` | How many times output verification made the model correct a price or ticket (details in the comment) |
| `guardrail_entrada` | Input guardrail flags: `card`, `cpf`, `injection`, `truncated` |
| `custo_provedor_usd` | Cost reported by OpenRouter |

This answers production questions such as: which questions end in the fallback? how often does
the model invent prices? how many manipulation attempts per day? how much does each conversation
cost?

**Local Langfuse, no account needed.** Compose includes a full Langfuse stack (`observability`
profile), with organization, project, keys and user created automatically:

```bash
docker compose --profile observability up   # agent on :8501 and Langfuse on :3000
```

Uncomment the three `LANGFUSE_*` lines from `.env.example` in your `.env` and log in at
http://localhost:3000 with `admin@emporio.local` / `emporio-local`. Inside Compose, the containers
reach Langfuse over the internal network (`langfuse-web:3000`), already configured. Without the
keys, tracing is off and the agent works the same.

**Privacy.** Card numbers, e-mails, phones and CPFs are masked **before** leaving the process,
using the SDK's `mask` parameter. This was verified directly in Langfuse's database (ClickHouse):
in a conversation containing all of that data, none of the trace's 10 records contained it. This
check caught a bug: the card number appeared in 2 records, because tracing captures the graph's
input **before** the guardrail masks the message. The tracing mask now covers card numbers too.

## Continuous integration

The [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) workflow runs on every push and pull
request, **without an API key**:

| Job | Steps |
|---|---|
| `test` | `ruff check` (lint); `pytest` (300+ tests, with a scripted model); regenerates the processed data and requires the versioned data quality report to be identical (ensures the pipeline is deterministic and the report is up to date); retrieval evaluation on the validation set in BM25 mode |
| `docker` | Builds the images; runs the tests inside the container; starts the web interface and waits for the healthcheck |

Evaluations that call the model (`emporio-eval-agent`, embeddings) stay out of CI: they cost
credit and vary between runs. They are run on demand, and results are stored in `evals/results/`.
