"""Testes do agente (grafo LangGraph) com um modelo roteirizado, sem chamadas de rede.

O modelo falso devolve respostas pré-definidas, inclusive chamadas de ferramenta; as
ferramentas, o repositório e a busca no manual são os reais.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from emporio.agent import EmporioAgent
from emporio.agent.graph import FALLBACK_ERROR, FALLBACK_LOOP, message_text, recent_history
from emporio.agent.prompts import build_system_prompt
from emporio.business_hours import STORE_TZ
from emporio.config import Settings
from emporio.rag.retriever import PolicyRetriever, load_chunks
from emporio.repository import StoreRepository

NOW = datetime(2026, 3, 2, 10, 30, tzinfo=STORE_TZ)  # segunda-feira, loja aberta


class ScriptedChatModel(BaseChatModel):
    """Devolve as respostas na ordem; guarda as mensagens recebidas em cada chamada."""

    responses: list[Any]  # AIMessage ou Exception (Any evita coerção do Pydantic)
    received: list[list[BaseMessage]] = Field(default_factory=list)
    repeat_last: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.received.append(list(messages))
        response = self.responses[0] if self.repeat_last and len(self.responses) == 1 else self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        # Como um modelo real, cada resposta tem ids novos (o LangGraph deduplica mensagens por id).
        fresh_calls = [{**c, "id": f"call_{uuid.uuid4().hex[:8]}"} for c in response.tool_calls]
        response = response.model_copy(update={"id": None, "tool_calls": fresh_calls})
        return ChatResult(generations=[ChatGeneration(message=response)])


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def make_agent(repo: StoreRepository, database_path: Path):
    policies = PolicyRetriever(load_chunks(database_path.parent / "policy_sections.json"), mode="bm25")

    def factory(*responses: AIMessage | Exception, repeat_last: bool = False) -> tuple[EmporioAgent, ScriptedChatModel]:
        model = ScriptedChatModel(responses=list(responses), repeat_last=repeat_last)
        agent = EmporioAgent(
            Settings(_env_file=None), model=model, repo=repo, policies=policies, clock=lambda: NOW
        )
        return agent, model

    return factory


# --- Fluxo principal -----------------------------------------------------------------


def test_tool_call_then_answer(make_agent) -> None:
    agent, model = make_agent(
        tool_call("get_product_details", {"name": "Takamine GD20"}),
        AIMessage("O Takamine GD20 sai por R$ 2.199,00 (R$ 2.089,05 no PIX)."),
    )
    reply = agent.new_session().send("Quanto custa o Takamine GD20?")

    assert reply.text.startswith("O Takamine GD20") and not reply.error
    assert [c.name for c in reply.tool_calls] == ["get_product_details"]
    assert "R$ 2.199,00" in reply.tool_calls[0].output  # resultado real da ferramenta

    first_call, second_call = model.received
    assert isinstance(first_call[0], SystemMessage) and "02/03/2026" in first_call[0].text
    assert isinstance(second_call[-1], ToolMessage)  # o modelo recebeu o resultado


def test_policy_tool_through_graph(make_agent) -> None:
    agent, _ = make_agent(
        tool_call("search_policies", {"query": "posso devolver?"}),
        AIMessage("Você tem 7 dias corridos após o recebimento."),
    )
    reply = agent.new_session().send("Me arrependi, posso devolver?")
    assert '"section":"4.1"' in reply.tool_calls[0].output


def test_conversation_memory(make_agent) -> None:
    agent, model = make_agent(AIMessage("Oi! Como posso ajudar?"), AIMessage("Claro, Ana!"))
    session = agent.new_session()
    session.send("Oi, sou a Ana")
    session.send("Lembra meu nome?")
    second_turn = model.received[1]
    assert any(isinstance(m, HumanMessage) and "Ana" in m.content for m in second_turn)
    assert len(session.history()) == 4  # 2 do cliente + 2 da assistente


def test_sessions_are_isolated(make_agent) -> None:
    agent, model = make_agent(AIMessage("Resposta A"), AIMessage("Resposta B"))
    a, b = agent.new_session(), agent.new_session()
    a.send("mensagem da conversa A")
    b.send("mensagem da conversa B")
    assert not any("conversa A" in str(m.content) for m in model.received[1])
    assert a.tool_context is not b.tool_context  # tentativas de verificação são por conversa


def test_auth_attempts_persist_within_session(make_agent) -> None:
    calls = [tool_call("get_order_status", {"order_id": 8, "email": f"x{i}@y.com"}, f"c{i}") for i in range(3)]
    replies = [AIMessage("Dados não conferem.") for _ in range(3)]
    agent, _ = make_agent(*[m for pair in zip(calls, replies, strict=True) for m in pair])
    session = agent.new_session()
    for _ in range(3):
        session.send("meu pedido é o 8")
    assert session.tool_context.auth_locked


# --- Falhas ----------------------------------------------------------------------------


def test_model_error_returns_fallback(make_agent) -> None:
    agent, _ = make_agent(RuntimeError("402 sem crédito"))
    reply = agent.new_session().send("Oi")
    assert reply.error and reply.text == FALLBACK_ERROR


def test_session_recovers_after_error(make_agent) -> None:
    agent, _ = make_agent(RuntimeError("instável"), AIMessage("Agora foi!"))
    session = agent.new_session()
    assert session.send("Oi").error
    assert session.send("Oi de novo").text == "Agora foi!"


def test_tool_loop_is_capped(make_agent) -> None:
    agent, _ = make_agent(tool_call("list_categories", {}), repeat_last=True)
    reply = agent.new_session().send("me mostra tudo")
    assert reply.error and reply.text == FALLBACK_LOOP


def test_empty_answer_returns_fallback(make_agent) -> None:
    agent, _ = make_agent(AIMessage(""))
    assert agent.new_session().send("Oi").error


def test_invalid_tool_args_do_not_crash(make_agent) -> None:
    agent, _ = make_agent(
        tool_call("payment_options", {}),  # faltam product_ids/amount
        AIMessage("Pode me dizer qual produto?"),
    )
    reply = agent.new_session().send("em quantas vezes?")
    assert not reply.error and "inválidos" in reply.tool_calls[0].output


# --- Utilitários e prompt ----------------------------------------------------------------


def test_recent_history_starts_at_customer_message() -> None:
    messages = [HumanMessage("1"), tool_call("x", {}), ToolMessage("r", tool_call_id="call_1"),
                AIMessage("a"), HumanMessage("2"), AIMessage("b")]
    window = recent_history(messages, limit=4)
    assert isinstance(window[0], HumanMessage) and window[0].content == "2"
    assert recent_history(messages, limit=10) == messages


def test_message_text_handles_content_blocks() -> None:
    assert message_text(AIMessage(content=[{"type": "text", "text": "Olá "}, {"type": "text", "text": "!"}])) == "Olá !"


def test_prompt_open_store() -> None:
    prompt = build_system_prompt(NOW)
    assert "segunda-feira, 02/03/2026, 10:30" in prompt and "ABERTA e fecha às 18:00" in prompt
    assert "(67) 3341-4444" in prompt and "3321-4500" not in prompt  # só o número canônico


def test_prompt_closed_store() -> None:
    prompt = build_system_prompt(datetime(2026, 3, 8, 15, 0, tzinfo=STORE_TZ))  # domingo
    assert "FECHADA" in prompt and "amanhã às 09:00" in prompt


def test_prompt_holiday() -> None:
    prompt = build_system_prompt(datetime(2026, 4, 3, 11, 0, tzinfo=STORE_TZ))
    assert "feriado: Sexta-feira Santa" in prompt


# --- Cache de prompt -----------------------------------------------------------------------


def test_static_prompt_has_no_date_and_is_stable() -> None:
    from emporio.agent.prompts import static_prompt

    assert "02/03/2026" not in static_prompt() and "ABERTA" not in static_prompt()
    assert static_prompt() == static_prompt()  # idêntico entre mensagens: pré-requisito do cache


def test_cached_system_prompt_marks_only_static_part() -> None:
    from emporio.agent.graph import system_prompt_for_turn

    message = system_prompt_for_turn(NOW, ["aviso do turno"], cache=True)
    static, dynamic = message.content
    assert static["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in dynamic
    assert "02/03/2026" in dynamic["text"] and "aviso do turno" in dynamic["text"]
    plain = system_prompt_for_turn(NOW, [], cache=False)
    assert isinstance(plain.content, str) and "02/03/2026" in plain.content


def test_cache_can_be_disabled(make_agent) -> None:
    agent, model = make_agent(AIMessage("Oi!"))
    agent.settings = agent.settings.model_copy(update={"llm_prompt_cache": False})
    agent.new_session().send("Oi")
    assert isinstance(model.received[0][0].content, str)
