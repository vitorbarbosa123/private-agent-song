# Instalação e configuração

[← Voltar ao README](../README.md)

## Como rodar

### Com Docker (recomendado)

Pré-requisitos: Docker com Compose v2.

```bash
cp .env.example .env              # preencha LLM_API_KEY (chave do OpenRouter)
docker compose up --build         # web em http://localhost:8501 e API em http://localhost:8710/docs
```

Os demais comandos rodam em containers da mesma imagem:

```bash
docker compose run --rm chat                     # chat no terminal (aceita --now, --debug, --session…)
docker compose run --rm tests                    # testes (não precisam de chave de API)
docker compose run --rm llm-check                # confere a configuração do modelo
docker compose run --rm eval --judge --judge-model google/gemini-2.5-pro   # avaliação do agente
docker compose run --rm eval-retrieval --dataset holdout                   # avaliação da busca
docker compose run --rm handoffs                 # painel da equipe no terminal
```

A imagem gera os dados tratados durante o build (o pipeline é determinístico e não precisa de
chave). Histórico das conversas e atendimentos ficam no volume `emporio-state`, compartilhado
entre a interface web e o terminal. O container roda com um usuário sem privilégios, e o `.env`
nunca entra na imagem: é lido em tempo de execução.

### Localmente, com uv

Pré-requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # cria o ambiente virtual e instala as dependências
cp .env.example .env       # e preencha LLM_API_KEY (chave do OpenRouter)
uv run emporio-clean-data  # trata os dados brutos e grava os artefatos em data/processed/
uv run streamlit run src/emporio/ui/app.py   # interface web
uv run emporio-llm-check   # confere a configuração e faz uma chamada mínima ao modelo
uv run emporio-eval-retrieval [--dataset holdout]  # avalia a busca no manual de políticas
uv run emporio-chat        # conversa com a assistente no terminal
uv run emporio-eval-agent [--judge]  # avaliação de ponta a ponta com 28 conversas de teste
uv run emporio-handoffs    # painel da equipe: atendimentos encaminhados pela assistente
uv run pytest              # roda os testes (não fazem chamadas ao modelo)
```

## Modelo de linguagem: como trocar

O projeto acessa o modelo pelo **[OpenRouter](https://openrouter.ai)**, com uma única chave de API.
O modelo padrão é um **preset** da plataforma (`@preset/emporio-agent`): modelo principal,
fallbacks e parâmetros ficam configurados no painel do OpenRouter, sem mudança de código.

**Para testar outro modelo, basta alterar uma variável no `.env`:**

```bash
LLM_MODEL=openai/gpt-4o-mini            # qualquer ID de https://openrouter.ai/models
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_MODEL=@preset/emporio-agent         # volta ao preset padrão
```

| Variável | Para quê | Padrão |
|---|---|---|
| `LLM_API_KEY` (ou `OPENROUTER_API_KEY`) | Chave de API | — |
| `LLM_MODEL` | Modelo do agente | `@preset/emporio-agent` |
| `LLM_FAST_MODEL` | Modelo barato para tarefas auxiliares (guardrails, avaliação) | usa `LLM_MODEL` |
| `LLM_FALLBACK_MODELS` | Fallbacks na própria requisição, separados por vírgula (só OpenRouter) | nenhum |
| `LLM_BASE_URL` | Qualquer API compatível com a da OpenAI: OpenAI direto, Ollama local etc. | OpenRouter |
| `LLM_MAX_TOKENS` | Limite de tokens da resposta. Sem ele, o OpenRouter reserva crédito para o máximo do modelo e pode recusar a chamada em chaves com limite de gasto | `1024` |
| `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Ajustes finos | `0.2`, `60`, `2` |
| `EMBEDDING_MODEL` | Modelo de embeddings da busca no manual (mesma chave e endpoint). Vazio = só BM25, sem rede | `google/gemini-embedding-001` |
| `RETRIEVAL_MODE` | `embeddings`, `hybrid` ou `bm25` | `embeddings` |
| `EMPORIO_STATE_DIR` | Onde ficam o histórico das conversas e os atendimentos encaminhados (SQLite) | `var/` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Ativam o rastreamento no Langfuse (ver [Observabilidade](08-operacao.md#observabilidade-langfuse)) | desligado |
| `LLM_PROMPT_CACHE` | Marca a parte fixa do system prompt para cache do provedor | `true` |
| `EMPORIO_API_KEY` | Se definida, a API REST exige o cabeçalho `X-API-Key` | sem autenticação |
| `EMPORIO_NOW` | Fixa a data e hora vistas pelo agente (ex.: `2026-03-02T10:30`), para demonstrações reproduzíveis | relógio real |

Exemplo com modelo local, sem chave: `LLM_BASE_URL=http://localhost:11434/v1` e
`LLM_MODEL=llama3.1`. O comando `uv run emporio-llm-check` mostra a configuração ativa (com a
chave mascarada) e testa uma chamada simples e outra **com ferramentas**, de que o agente depende.
Para cada uma, informa qual modelo de fato atendeu, o que é útil para confirmar um fallback. Em
caso de erro, dá dicas para os problemas mais comuns do OpenRouter: crédito, chave inválida ou
guardrails de privacidade do workspace que excluem os endpoints do modelo.

**Por que OpenRouter.** Uma única chave e uma API compatível com a da OpenAI dão acesso a modelos
de vários fornecedores. Isso permite trocar ou comparar modelos sem mexer em código e configurar
fallbacks automáticos se um provedor cair. Como o cliente (`langchain-openai`) fala o protocolo
da OpenAI, o mesmo código funciona com outros provedores compatíveis. Toda a configuração está em
[`src/emporio/config.py`](../src/emporio/config.py) e a criação do cliente em
[`src/emporio/llm.py`](../src/emporio/llm.py).
