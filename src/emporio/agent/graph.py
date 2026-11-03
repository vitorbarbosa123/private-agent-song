"""Agente de atendimento: grafo ReAct em LangGraph.

    START → agent ⇄ tools → (resposta)

- `agent`: o LLM recebe o system prompt (montado a cada turno, com data/hora e status da
  loja) e o histórico, e decide entre responder ou chamar ferramentas.
- `tools`: executa as ferramentas pedidas e devolve os resultados ao `agent`.

O grafo é montado à mão (em vez do agente pronto do LangGraph) para que guardrails de
entrada/saída e o handoff para humanos possam entrar como nós explícitos.

Cada conversa (`ChatSession`) tem o seu próprio `ToolContext`, porque o contador de
tentativas de verificação de identidade é por conversa. Modelo, repositório, busca no
manual e checkpointer são compartilhados.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from emporio.agent.prompts import build_system_prompt
from emporio.business_hours import Clock, make_clock
from emporio.config import Settings, get_settings
from emporio.llm import build_chat_model
from emporio.policy_rules import STORE_INFO
from emporio.rag.retriever import PolicyRetriever
from emporio.repository import StoreRepository, open_repository
from emporio.tools import ToolContext, build_tools

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40  # janela de contexto enviada ao modelo
RECURSION_LIMIT = 16  # ~7 rodadas de ferramenta por mensagem do cliente

FALLBACK_ERROR = (
    "Poxa, tive um problema técnico aqui e não consegui concluir sua solicitação. 😕 "
    f"Pode tentar de novo em instantes? Se preferir, fale com a equipe pelo {STORE_INFO['phone_whatsapp']}."
)
FALLBACK_LOOP = (
    "Desculpa, não consegui chegar a uma resposta segura para isso. Vou deixar com a equipe: "
    f"fale com a gente pelo {STORE_INFO['phone_whatsapp']}, de segunda a sexta das 9h às 18h "
    "e sábado das 9h às 13h."
)


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    output: str


@dataclass
class AgentReply:
    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    error: bool = False


def recent_history(messages: list[AnyMessage], limit: int = MAX_HISTORY_MESSAGES) -> list[AnyMessage]:
    """Últimas mensagens, começando sempre numa mensagem do cliente para não cortar um par
    chamada de ferramenta / resultado ao meio (os provedores rejeitam pares incompletos)."""
    if len(messages) <= limit:
        return messages
    window = messages[-limit:]
    for i, message in enumerate(window):
        if isinstance(message, HumanMessage):
            return window[i:]
    return window[-1:]


def build_graph(model: BaseChatModel, tools: list[BaseTool], clock: Clock, checkpointer: BaseCheckpointSaver):
    bound = model.bind_tools(tools)

    def agent_node(state: MessagesState) -> dict[str, list[AnyMessage]]:
        system = SystemMessage(build_system_prompt(clock()))
        response = bound.invoke([system, *recent_history(state["messages"])])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)


def message_text(message: AIMessage) -> str:
    """Texto de uma resposta, inclusive quando o provedor devolve blocos de conteúdo."""
    if isinstance(message.content, str):
        return message.content.strip()
    parts = [b.get("text", "") for b in message.content if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(parts).strip()


class EmporioAgent:
    """Recursos compartilhados entre conversas. Use `new_session()` para cada cliente."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        model: BaseChatModel | None = None,
        repo: StoreRepository | None = None,
        policies: PolicyRetriever | None = None,
        clock: Clock | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        s = settings or get_settings()
        self.settings = s
        self.model = model or build_chat_model(s)
        self.repo = repo or open_repository(s)
        self.policies = policies if policies is not None else PolicyRetriever.from_settings(s)
        self.clock = clock or make_clock(s)
        self.checkpointer = checkpointer or InMemorySaver()

    def new_session(self, thread_id: str | None = None) -> ChatSession:
        return ChatSession(self, thread_id or uuid.uuid4().hex)


class ChatSession:
    def __init__(self, agent: EmporioAgent, thread_id: str) -> None:
        self.thread_id = thread_id
        self.tool_context = ToolContext(repo=agent.repo, clock=agent.clock, policies=agent.policies)
        self.graph = build_graph(agent.model, build_tools(self.tool_context), agent.clock, agent.checkpointer)

    @property
    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.thread_id}, "recursion_limit": RECURSION_LIMIT}

    def history(self) -> list[AnyMessage]:
        return self.graph.get_state(self._config).values.get("messages", [])

    def send(self, message: str) -> AgentReply:
        try:
            result = self.graph.invoke({"messages": [HumanMessage(message)]}, self._config)
        except GraphRecursionError:
            logger.warning("Limite de iterações atingido na conversa %s", self.thread_id)
            return AgentReply(FALLBACK_LOOP, error=True)
        except Exception as exc:
            # Uma linha no log; o traceback completo só em nível DEBUG (emporio-chat --debug).
            logger.error("Falha ao processar mensagem (%s): %s", type(exc).__name__, str(exc)[:300],
                         exc_info=logger.isEnabledFor(logging.DEBUG))
            return AgentReply(FALLBACK_ERROR, error=True)

        messages: list[AnyMessage] = result["messages"]
        last_human = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        turn = messages[last_human + 1 :]
        outputs = {m.tool_call_id: str(m.content) for m in turn if isinstance(m, ToolMessage)}
        calls = [
            ToolCallRecord(call["name"], call["args"], outputs.get(call["id"], ""))
            for m in turn if isinstance(m, AIMessage)
            for call in m.tool_calls
        ]
        final = turn[-1] if turn and isinstance(turn[-1], AIMessage) else None
        text = message_text(final) if final else ""
        if not text:
            logger.warning("Resposta vazia do modelo na conversa %s", self.thread_id)
            return AgentReply(FALLBACK_ERROR, calls, error=True)
        return AgentReply(text, calls)


def create_agent(settings: Settings | None = None) -> EmporioAgent:
    """Agente com a configuração do ambiente (.env)."""
    return EmporioAgent(settings)
