"""Testes da reconstrução de histórico usada pelas interfaces (sem rede)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from emporio.agent.history import conversation_turns
from emporio.agent.memory import list_sessions
from emporio.repository import StoreRepository
from tests.test_agent import tool_call
from tests.test_memory_handoff import _agent


def test_conversation_turns_groups_tools_and_reply() -> None:
    messages = [
        HumanMessage("Vocês estão abertos?"),
        AIMessage("", tool_calls=[{"name": "store_status", "args": {}, "id": "c1"}]),
        ToolMessage('{"is_open": true}', tool_call_id="c1", name="store_status"),
        AIMessage("Estamos abertos até as 18h!"),
        HumanMessage("Obrigado"),
        AIMessage("Imagina!"),
    ]
    first, second = conversation_turns(messages)
    assert first.user == "Vocês estão abertos?" and first.reply == "Estamos abertos até as 18h!"
    assert [(c.name, c.output) for c in first.tool_calls] == [("store_status", '{"is_open": true}')]
    assert second.reply == "Imagina!" and second.tool_calls == []


def test_conversation_turns_from_real_session(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo,
                   tool_call("get_product_details", {"name": "Takamine GD20"}),
                   AIMessage("Custa R$ 2.199,00."))
    session = agent.new_session("t1")
    session.send("Quanto custa o Takamine GD20?")
    (turn,) = conversation_turns(session.history())
    assert turn.reply == "Custa R$ 2.199,00."
    assert turn.tool_calls[0].name == "get_product_details" and "2.199,00" in turn.tool_calls[0].output


def test_session_title_is_first_customer_message(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo, AIMessage("a"), AIMessage("b"))
    long_question = "Quero saber quais violões de nylon vocês têm para iniciantes com bom custo-benefício"
    session = agent.new_session("t2")
    session.send(long_question)
    session.send("outra pergunta")
    (info,) = list_sessions(agent.checkpointer)
    assert info.title.startswith("Quero saber quais violões") and info.title.endswith("…")
    assert len(info.title) <= 48
