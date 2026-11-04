"""Agente de atendimento: grafo ReAct em LangGraph com guardrails.

    START → input_guard → agent ⇄ tools → (resposta verificada)

- `input_guard`: mascara cartão/CPF antes de a mensagem entrar no histórico, detecta
  tentativas de manipulação e trunca mensagens longas (ver `guards.py`).
- `agent`: o LLM recebe o system prompt (montado a cada turno, com data/hora, status da
  loja e avisos do guardrail) e o histórico, e decide entre responder ou chamar
  ferramentas. A resposta final é verificada: protocolos e preços citados precisam ter
  vindo das ferramentas (ver `verification.py`).
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

from emporio.agent.guards import check_input, required_warnings
from emporio.agent.prompts import build_system_prompt
from emporio.agent.verification import correction_message, verify_reply
from emporio.business_hours import Clock, make_clock
from emporio.config import Settings, get_settings
from emporio.handoff import HandoffStore
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
FALLBACK_UNGROUNDED_TICKET = (
    "Desculpa, não consegui registrar o seu atendimento agora. Para garantir que a equipe veja o "
    f"seu caso, fale com a gente pelo WhatsApp {STORE_INFO['phone_whatsapp']}."
)
FALLBACK_UNGROUNDED_PRICE = (
    "Desculpa, quero te passar os valores certinhos e não consegui confirmar agora. Pode me "
    f"perguntar de novo? Se preferir, a equipe confirma pelo WhatsApp {STORE_INFO['phone_whatsapp']}."
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
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # custo informado pelo provedor (OpenRouter), se houver
    model: str | None = None  # modelo que de fato respondeu (com presets/fallbacks pode variar)


def turn_usage(messages: list[AnyMessage]) -> tuple[int, int, float | None]:
    """Tokens e custo somados das respostas do modelo neste turno."""
    tokens_in = tokens_out = 0
    cost: float | None = None
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        if m.usage_metadata:
            tokens_in += m.usage_metadata.get("input_tokens", 0)
            tokens_out += m.usage_metadata.get("output_tokens", 0)
        if (c := (m.response_metadata.get("token_usage") or {}).get("cost")) is not None:
            cost = (cost or 0.0) + float(c)
    return tokens_in, tokens_out, cost


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


class AgentState(MessagesState):
    # Avisos do guardrail de entrada para o turno atual (sobrescritos a cada mensagem).
    guard_notes: list[str]
    guard_flags: list[str]


def input_guard_node(state: AgentState) -> dict[str, Any]:
    last = state["messages"][-1]
    if not isinstance(last, HumanMessage):
        return {"guard_notes": [], "guard_flags": []}
    check = check_input(str(last.content))
    update: dict[str, Any] = {"guard_notes": check.notes, "guard_flags": sorted(check.flags)}
    if check.flags:
        logger.info("Guardrail de entrada: %s", ", ".join(sorted(check.flags)))
    if check.text != last.content:
        # Mesmo id: substitui a mensagem original no histórico, que nunca é gravada sem máscara.
        update["messages"] = [HumanMessage(content=check.text, id=last.id)]
    return update


def system_prompt_for_turn(now_prompt: str, notes: list[str]) -> SystemMessage:
    if not notes:
        return SystemMessage(now_prompt)
    warnings = "\n".join(f"- {note}" for note in notes)
    return SystemMessage(f"{now_prompt}\n# Avisos sobre a mensagem atual\n{warnings}\n")


def build_graph(model: BaseChatModel, tools: list[BaseTool], clock: Clock, checkpointer: BaseCheckpointSaver):
    bound = model.bind_tools(tools)

    def agent_node(state: AgentState) -> dict[str, list[AnyMessage]]:
        system = system_prompt_for_turn(build_system_prompt(clock()), state.get("guard_notes") or [])
        history = recent_history(state["messages"])
        response = bound.invoke([system, *history])
        if response.tool_calls:
            return {"messages": [response]}

        # Verificação de saída: protocolos e preços citados precisam ter vindo das ferramentas.
        issues = verify_reply(message_text(response), state["messages"])
        if issues:
            logger.warning("Resposta com dados não verificados: %s; pedindo correção.", issues)
            # A correção não é salva no histórico: só vale para esta nova tentativa.
            response = bound.invoke([system, *history, response, correction_message(issues)])
            remaining = [] if response.tool_calls else verify_reply(message_text(response), state["messages"])
            if remaining:
                logger.error("Modelo insistiu em dados não verificados (%s); usando resposta segura.", remaining)
                kinds = {issue.kind for issue in remaining}
                response = AIMessage(FALLBACK_UNGROUNDED_TICKET if "ticket" in kinds else FALLBACK_UNGROUNDED_PRICE)

        # Avisos obrigatórios (cartão, CPF) que o modelo não incluiu são acrescentados.
        if not response.tool_calls:
            if missing := required_warnings(state.get("guard_flags") or [], message_text(response)):
                response = AIMessage(content="\n\n".join([*missing, message_text(response)]), id=response.id)
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("input_guard", input_guard_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "input_guard")
    graph.add_edge("input_guard", "agent")
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
        handoffs: HandoffStore | None = None,
    ) -> None:
        s = settings or get_settings()
        self.settings = s
        self.model = model or build_chat_model(s)
        self.repo = repo or open_repository(s)
        self.policies = policies if policies is not None else PolicyRetriever.from_settings(s)
        self.clock = clock or make_clock(s)
        self.checkpointer = checkpointer or InMemorySaver()
        self.handoffs = handoffs or HandoffStore(":memory:")

    def new_session(self, thread_id: str | None = None) -> ChatSession:
        return ChatSession(self, thread_id or uuid.uuid4().hex)


class ChatSession:
    def __init__(self, agent: EmporioAgent, thread_id: str) -> None:
        self.thread_id = thread_id
        self.checkpointer = agent.checkpointer
        self.tool_context = ToolContext(
            repo=agent.repo, clock=agent.clock, policies=agent.policies,
            handoffs=agent.handoffs, session_id=thread_id,
        )
        self.graph = build_graph(agent.model, build_tools(self.tool_context), agent.clock, agent.checkpointer)

    @property
    def _config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.thread_id}, "recursion_limit": RECURSION_LIMIT}

    def history(self) -> list[AnyMessage]:
        return self.graph.get_state(self._config).values.get("messages", [])

    def forget(self) -> None:
        """Apaga o histórico desta conversa (pedido do cliente, LGPD)."""
        self.checkpointer.delete_thread(self.thread_id)

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
        usage = turn_usage(turn)
        served_by = next((m.response_metadata.get("model_name") for m in reversed(turn)
                          if isinstance(m, AIMessage) and m.response_metadata.get("model_name")), None)
        if not text:
            logger.warning("Resposta vazia do modelo na conversa %s", self.thread_id)
            return AgentReply(FALLBACK_ERROR, calls, True, *usage, model=served_by)
        return AgentReply(text, calls, False, *usage, model=served_by)


def create_agent(settings: Settings | None = None, *, persistent: bool = True) -> EmporioAgent:
    """Agente com a configuração do ambiente (.env).

    Com `persistent=True`, o histórico das conversas e os atendimentos encaminhados ficam
    em SQLite no diretório de estado (`EMPORIO_STATE_DIR`, padrão `var/`).
    """
    s = settings or get_settings()
    if not persistent:
        return EmporioAgent(s)
    from emporio.agent.memory import open_checkpointer

    return EmporioAgent(s, checkpointer=open_checkpointer(s.conversations_path),
                        handoffs=HandoffStore(s.handoffs_path))
