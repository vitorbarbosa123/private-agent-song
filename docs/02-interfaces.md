# Interfaces: web, terminal and API

[← Back to README](../README.md)

## Web interface

`docker compose up` (or `uv run streamlit run src/emporio/ui/app.py`) opens the interface at
http://localhost:8501. It follows the layout of current AI chat apps:

- **Conversations in the sidebar,** titled with the first question. You can start a new one,
  resume any previous conversation and delete the current one (right to erasure, LGPD).
- **Persistent history** in the same SQLite database used by the terminal.
- **Tools called in each reply:** an expandable panel shows which tools the assistant used, the
  arguments sent and the result received. It makes the agent's decisions easy to understand and
  audit. It can be turned off in the sidebar.
- **Starter suggestions** with the four questions from the case.
- **Simulated date and time,** useful because the orders in the dataset are from 2025-2026 (e.g.
  to test the return deadline or the store being closed on a Sunday).
- **"Atendimentos" (cases) page:** the staff sees and closes cases escalated by the assistant.

The interface was tested end to end with Streamlit's `AppTest` inside the container: clicking a
suggestion, a real model reply, the tool panel, the conversation in the sidebar and a second turn
that relies on context ("and in how many installments can I pay for *it*?").

## Terminal chat

```bash
uv run emporio-chat                          # interactive chat
uv run emporio-chat --debug                  # shows tool calls and their results
uv run emporio-chat --now 2026-03-02T10:30   # simulated date/time (orders are from 2025-2026)
uv run emporio-chat --model openai/gpt-4o-mini            # try another model without editing .env
uv run emporio-chat -m "Oi" -m "Quanto custa o Takamine GD20?"  # non-interactive script
uv run emporio-chat --sessions               # lists saved conversations
uv run emporio-chat --session <id>           # resumes a conversation (the id is shown on exit)
uv run emporio-chat --no-persist             # does not save history or cases
uv run emporio-handoffs [--all] [--close N]  # staff: lists and closes escalated cases
```

During the chat: `/novo` starts a new conversation, `/esquecer` deletes the current conversation's
history, `/debug` toggles details, `/sair` exits.

Test data for order lookups (fictional, from `data/`): order **8** with the e-mail
`anacarol.ferreira@coldmail.com` (shipped, with tracking) or order **7** with
`leticia.rocha@jmail.com` (delivered). With `--now 2026-02-20T10:00`, order 7 is still within the
withdrawal period.

## REST API

`docker compose up` also starts an API (FastAPI) at http://localhost:8710, with interactive docs
at `/docs`. It is the integration point for real channels (WhatsApp Business, website, CRM) and
shares conversations and cases with the web interface and the terminal.

| Endpoint | Purpose |
|---|---|
| `POST /conversations` | Creates a conversation |
| `GET /conversations` | Lists conversations (with titles) |
| `POST /conversations/{id}/messages` | Sends the customer's message and returns the reply; `?include_tools=true` includes the tools called |
| `GET /conversations/{id}` | History as turns |
| `DELETE /conversations/{id}` | Deletes the conversation (LGPD) |
| `GET /handoffs`, `POST /handoffs/{id}/close` | Cases escalated to the team |
| `GET /health` | Healthcheck (public) |

```bash
curl -s -X POST localhost:8710/conversations/my-conversation/messages \
  -H 'Content-Type: application/json' -d '{"message": "Quanto custa o Takamine GD20?"}'
```

With `EMPORIO_API_KEY` set, every route (except `/health`) requires the `X-API-Key` header. In
Compose the port is bound to `localhost` only and is configurable (`EMPORIO_API_PORT`). Provider
failures do not become HTTP errors: the response carries the fallback message with
`"error": true`, so the channel can decide what to do.
