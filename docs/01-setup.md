# Setup and configuration

[← Back to README](../README.md)

## How to run

### With Docker (recommended)

Requirements: Docker with Compose v2.

```bash
cp .env.example .env              # fill in LLM_API_KEY (OpenRouter key)
docker compose up --build         # web at http://localhost:8501 and API at http://localhost:8710/docs
```

The other commands run in containers built from the same image:

```bash
docker compose run --rm chat                     # terminal chat (accepts --now, --debug, --session…)
docker compose run --rm tests                    # tests (no API key needed)
docker compose run --rm llm-check                # checks the model configuration
docker compose run --rm eval --judge --judge-model google/gemini-2.5-pro   # agent evaluation
docker compose run --rm eval-retrieval --dataset holdout                   # retrieval evaluation
docker compose run --rm handoffs                 # staff panel in the terminal
```

The image generates the processed data at build time (the pipeline is deterministic and needs no
key). Conversation history and escalated cases live in the `emporio-state` volume, shared by the
web interface and the terminal. The container runs as an unprivileged user, and `.env` never goes
into the image: it is read at runtime.

### Locally, with uv

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # creates the virtual environment and installs dependencies
cp .env.example .env       # and fill in LLM_API_KEY (OpenRouter key)
uv run emporio-clean-data  # processes the raw data and writes the artifacts to data/processed/
uv run streamlit run src/emporio/ui/app.py   # web interface
uv run emporio-llm-check   # checks the configuration and makes a minimal model call
uv run emporio-eval-retrieval [--dataset holdout]  # evaluates policy retrieval
uv run emporio-chat        # chat with the assistant in the terminal
uv run emporio-eval-agent [--judge]  # end-to-end evaluation with 28 test conversations
uv run emporio-handoffs    # staff panel: cases escalated by the assistant
uv run pytest              # runs the tests (no model calls)
```

## Language model: how to switch

The project reaches the model through **[OpenRouter](https://openrouter.ai)** with a single API
key. The default model is a platform **preset** (`@preset/emporio-agent`): main model, fallbacks
and parameters are configured in the OpenRouter dashboard, with no code changes.

**To test another model, change one variable in `.env`:**

```bash
LLM_MODEL=openai/gpt-4o-mini            # any ID from https://openrouter.ai/models
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_MODEL=@preset/emporio-agent         # back to the default preset
```

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` (or `OPENROUTER_API_KEY`) | API key | — |
| `LLM_MODEL` | Agent model | `@preset/emporio-agent` |
| `LLM_FAST_MODEL` | Cheaper model for auxiliary tasks (evaluation judge) | uses `LLM_MODEL` |
| `LLM_FALLBACK_MODELS` | Per-request fallbacks, comma-separated (OpenRouter only) | none |
| `LLM_BASE_URL` | Any OpenAI-compatible API: OpenAI, Anthropic, local Ollama, etc. | OpenRouter |
| `LLM_MAX_TOKENS` | Reply token limit. Without it, OpenRouter reserves credit for the model's maximum and may reject calls from keys with a spending limit | `1024` |
| `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Fine tuning | `0.2`, `60`, `2` |
| `EMBEDDING_MODEL` | Embedding model for policy retrieval (same key and endpoint). Empty = BM25 only, no network | `google/gemini-embedding-001` |
| `RETRIEVAL_MODE` | `embeddings`, `hybrid` or `bm25` | `embeddings` |
| `EMPORIO_STATE_DIR` | Where conversation history and escalated cases are stored (SQLite) | `var/` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Enable Langfuse tracing (see [Observability](08-operations.md#observability-langfuse)) | off |
| `LLM_PROMPT_CACHE` | Marks the static part of the system prompt for provider caching (OpenRouter only) | `true` |
| `EMPORIO_API_KEY` | If set, the REST API requires the `X-API-Key` header | no auth |
| `EMPORIO_NOW` | Pins the date and time seen by the agent (e.g. `2026-03-02T10:30`) for reproducible demos | real clock |

Other providers, also commented in [`.env.example`](../.env.example):

- **Local model, no key:** `LLM_BASE_URL=http://localhost:11434/v1` and `LLM_MODEL=llama3.1`.
- **Anthropic API directly:** `LLM_BASE_URL=https://api.anthropic.com/v1/`, an Anthropic Console
  API key, `LLM_MODEL=claude-haiku-4-5` and an empty `EMBEDDING_MODEL` (Anthropic has no
  embeddings, so retrieval uses BM25).

`uv run emporio-llm-check` shows the active configuration (with the key masked) and tests both a
plain call and a call **with tools**, which the agent depends on. For each, it reports which model
actually answered, which helps confirm a fallback. On errors, it gives hints for the most common
OpenRouter problems: credit, invalid key, or workspace privacy guardrails that exclude the model's
endpoints.

**Why OpenRouter.** One key and an OpenAI-compatible API give access to models from many vendors.
That makes it possible to switch or compare models without touching code and to set up automatic
fallbacks if a provider goes down. Since the client (`langchain-openai`) speaks the OpenAI
protocol, the same code works with other compatible providers. All configuration is in
[`src/emporio/config.py`](../src/emporio/config.py) and the client is created in
[`src/emporio/llm.py`](../src/emporio/llm.py).

**Why Claude Haiku 4.5 in the preset.** It passed the live tool-calling tests, handles Brazilian
Portuguese well, and has endpoints compatible with the workspace's zero-data-retention policy
(the first preset model, `openai/gpt-4o-mini`, had no ZDR-compliant endpoint that supports
tools). The [model comparison](07-evaluation.md#model-comparison) shows that Gemini 2.5 Flash is a
strong, much cheaper alternative, pending a cross-family judge check.
