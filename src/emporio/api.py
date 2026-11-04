"""API REST da assistente (FastAPI): integração com WhatsApp Business, site ou CRM.

    uv run emporio-api                    # http://localhost:8000 (documentação em /docs)
    docker compose up                     # sobe junto da interface web

Autenticação opcional: se EMPORIO_API_KEY estiver definida, toda chamada (exceto /health)
precisa do cabeçalho `X-API-Key`.

Endpoints:
    POST   /conversations                      cria uma conversa
    GET    /conversations                      lista conversas
    POST   /conversations/{id}/messages        envia mensagem e recebe a resposta
    GET    /conversations/{id}                 histórico em turnos
    DELETE /conversations/{id}                 apaga a conversa (LGPD)
    GET    /handoffs                           atendimentos encaminhados à equipe
    POST   /handoffs/{ticket_id}/close         encerra um atendimento
"""

from __future__ import annotations

import os
import secrets
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from emporio.agent import ChatSession, EmporioAgent, create_agent
from emporio.agent.graph import ToolCallRecord
from emporio.agent.history import conversation_turns
from emporio.agent.memory import list_sessions
from emporio.llm import resolve_model

# --- Esquemas ------------------------------------------------------------------------------


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000, examples=["Quanto custa o Takamine GD20?"])


class ToolCallOut(BaseModel):
    name: str
    args: dict[str, Any]
    output: str


class ReplyOut(BaseModel):
    conversation_id: str
    reply: str
    error: bool
    tool_calls: list[ToolCallOut] | None = Field(default=None, description="Só com ?include_tools=true.")
    model: str | None = None
    cost_usd: float | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime
    messages: int


class TurnOut(BaseModel):
    user: str
    reply: str
    tool_calls: list[ToolCallOut]


class HandoffOut(BaseModel):
    id: int
    code: str
    created_at: datetime
    reason: str
    summary: str
    customer_name: str | None
    contact: str | None
    order_id: int | None
    status: str


def _tools(calls: list[ToolCallRecord]) -> list[ToolCallOut]:
    return [ToolCallOut(name=c.name, args=c.args, output=c.output) for c in calls]


# --- Aplicação -----------------------------------------------------------------------------


class SessionRegistry:
    """Uma ChatSession por conversa (guarda o limite de tentativas de verificação)."""

    def __init__(self, agent: EmporioAgent) -> None:
        self.agent = agent
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def get(self, conversation_id: str) -> ChatSession:
        with self._lock:
            if conversation_id not in self._sessions:
                self._sessions[conversation_id] = self.agent.new_session(conversation_id)
            return self._sessions[conversation_id]

    def forget(self, conversation_id: str) -> None:
        self.get(conversation_id).forget()
        with self._lock:
            self._sessions.pop(conversation_id, None)


def _registry(request: Request) -> SessionRegistry:
    return request.app.state.sessions


# No nível do módulo: com `from __future__ import annotations` o FastAPI resolve as anotações
# pelo nome no escopo global; um alias local viraria parâmetro de query.
Registry = Annotated[SessionRegistry, Depends(_registry)]


def create_app(agent: EmporioAgent | None = None, api_key: str | None = None) -> FastAPI:
    """`agent` permite injetar um agente de teste; sem ele, usa a configuração do .env."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.sessions = SessionRegistry(agent or create_agent(persistent=True))
        yield
        app.state.sessions.agent.tracer.flush()

    expected_key = api_key if api_key is not None else os.environ.get("EMPORIO_API_KEY") or None

    def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if expected_key and not (x_api_key and secrets.compare_digest(x_api_key, expected_key)):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key ausente ou inválida.")

    app = FastAPI(
        title="Empório da Música · Assistente Lia",
        version="1.0.0",
        description="Atendimento virtual da Empório da Música. Mensagens de clientes entram, respostas "
                    "verificadas saem; conversas e atendimentos ficam persistidos.",
        lifespan=lifespan,
    )
    protected = [Depends(require_key)]

    @app.get("/health", tags=["infra"])
    def health(reg: Registry) -> dict[str, str]:
        return {"status": "ok", "model": resolve_model(reg.agent.settings)}

    @app.post("/conversations", status_code=201, dependencies=protected, tags=["conversas"])
    def create_conversation() -> dict[str, str]:
        return {"id": uuid.uuid4().hex}

    @app.get("/conversations", dependencies=protected, tags=["conversas"])
    def list_conversations(reg: Registry, limit: int = Query(20, ge=1, le=100)) -> list[ConversationOut]:
        return [ConversationOut(id=s.thread_id, title=s.title, updated_at=s.updated_at, messages=s.messages)
                for s in list_sessions(reg.agent.checkpointer, limit=limit)]

    @app.post("/conversations/{conversation_id}/messages", dependencies=protected, tags=["conversas"])
    def send_message(conversation_id: str, body: MessageIn, reg: Registry,
                     include_tools: bool = Query(False, description="Inclui as ferramentas chamadas.")) -> ReplyOut:
        reply = reg.get(conversation_id).send(body.message)
        return ReplyOut(conversation_id=conversation_id, reply=reply.text, error=reply.error,
                        tool_calls=_tools(reply.tool_calls) if include_tools else None,
                        model=reply.model, cost_usd=reply.cost_usd)

    @app.get("/conversations/{conversation_id}", dependencies=protected, tags=["conversas"])
    def get_conversation(conversation_id: str, reg: Registry) -> list[TurnOut]:
        turns = conversation_turns(reg.get(conversation_id).history())
        if not turns:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")
        return [TurnOut(user=t.user, reply=t.reply, tool_calls=_tools(t.tool_calls)) for t in turns]

    @app.delete("/conversations/{conversation_id}", status_code=204, dependencies=protected, tags=["conversas"])
    def delete_conversation(conversation_id: str, reg: Registry) -> Response:
        reg.forget(conversation_id)
        return Response(status_code=204)

    @app.get("/handoffs", dependencies=protected, tags=["equipe"])
    def list_handoffs(reg: Registry, include_closed: bool = False) -> list[HandoffOut]:
        return [HandoffOut(id=t.id, code=t.code, created_at=t.created_at, reason=t.reason, summary=t.summary,
                           customer_name=t.customer_name, contact=t.contact, order_id=t.order_id, status=t.status)
                for t in reg.agent.handoffs.list(include_closed=include_closed)]

    @app.post("/handoffs/{ticket_id}/close", dependencies=protected, tags=["equipe"])
    def close_handoff(ticket_id: int, reg: Registry) -> dict[str, str]:
        if not reg.agent.handoffs.close(ticket_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Atendimento não encontrado ou já encerrado.")
        return {"status": "closed"}

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("EMPORIO_API_HOST", "127.0.0.1")
    port = int(os.environ.get("EMPORIO_API_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
