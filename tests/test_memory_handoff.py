"""Testes do histórico persistente e do encaminhamento para humanos (sem rede)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from emporio.agent import EmporioAgent
from emporio.agent.memory import list_sessions, open_checkpointer
from emporio.business_hours import STORE_TZ
from emporio.config import Settings
from emporio.handoff import HandoffStore
from emporio.repository import StoreRepository
from emporio.tools import ToolContext
from emporio.tools.handoff import EscalateInput, escalate_to_human
from tests.test_agent import ScriptedChatModel, tool_call

OPEN = datetime(2026, 3, 2, 10, 30, tzinfo=STORE_TZ)  # segunda, loja aberta
CLOSED = datetime(2026, 3, 7, 15, 0, tzinfo=STORE_TZ)  # sábado à tarde

CASE = {"summary": "Cliente relata que o violão do pedido 7 chegou com o tampo trincado.",
        "customer_name": "Letícia", "contact": "(67) 99789-0123", "order_id": 7}


# --- Registro de atendimentos ------------------------------------------------------------


def test_handoff_store_lifecycle(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path / "h.sqlite")
    ticket = store.create(session_id="s1", reason="defeito", now=OPEN, **CASE)
    assert ticket.code == "ATD-00001" and ticket.status == "open"
    assert store.find_open("s1", "defeito") == ticket
    assert store.close(ticket.id)
    assert not store.close(ticket.id)  # já encerrado
    assert store.list() == [] and len(store.list(include_closed=True)) == 1


def test_handoff_store_persists(tmp_path: Path) -> None:
    HandoffStore(tmp_path / "h.sqlite").create(session_id="s1", reason="reclamacao", now=OPEN, **CASE)
    assert len(HandoffStore(tmp_path / "h.sqlite").list()) == 1


@pytest.fixture
def make_ctx(repo: StoreRepository):
    def factory(now: datetime = OPEN, session_id: str = "s1") -> ToolContext:
        return ToolContext(repo=repo, clock=lambda: now, handoffs=HandoffStore(":memory:"), session_id=session_id)

    return factory


def test_escalate_requires_contact(make_ctx) -> None:
    ctx = make_ctx()
    result = escalate_to_human(ctx, EscalateInput(reason="defeito", summary=CASE["summary"]))
    assert result.status == "contact_required" and result.ticket is None
    assert ctx.handoffs.list() == []


def test_escalate_creates_ticket_during_business_hours(make_ctx) -> None:
    result = escalate_to_human(make_ctx(), EscalateInput(reason="defeito", **CASE))
    assert result.status == "created" and result.ticket == "ATD-00001"
    assert result.team_available_now and "ainda hoje" in result.expected_response


def test_escalate_when_closed_informs_next_opening(make_ctx) -> None:
    result = escalate_to_human(make_ctx(CLOSED), EscalateInput(reason="pedido_do_cliente", **CASE))
    assert not result.team_available_now
    assert "segunda-feira (09/03) às 09:00" in result.expected_response


def test_complaint_has_24_business_hours_sla(make_ctx) -> None:
    result = escalate_to_human(make_ctx(), EscalateInput(reason="reclamacao", **CASE))
    assert "24 horas úteis" in result.expected_response


def test_escalate_does_not_duplicate_open_ticket(make_ctx) -> None:
    ctx = make_ctx()
    first = escalate_to_human(ctx, EscalateInput(reason="defeito", **CASE))
    second = escalate_to_human(ctx, EscalateInput(reason="defeito", **CASE))
    assert second.status == "already_open" and second.ticket == first.ticket
    assert len(ctx.handoffs.list()) == 1


# --- Histórico persistente --------------------------------------------------------------


def _agent(tmp_path: Path, repo: StoreRepository, *responses: AIMessage) -> EmporioAgent:
    return EmporioAgent(
        Settings(_env_file=None),
        model=ScriptedChatModel(responses=list(responses)),
        repo=repo,
        policies=None,
        clock=lambda: OPEN,
        checkpointer=open_checkpointer(tmp_path / "conversations.sqlite"),
        handoffs=HandoffStore(tmp_path / "handoffs.sqlite"),
    )


def test_conversation_survives_restart(tmp_path: Path, repo: StoreRepository) -> None:
    first_run = _agent(tmp_path, repo, AIMessage("Oi, Ana! Como posso ajudar?"))
    session = first_run.new_session("cliente-ana")
    session.send("Oi, sou a Ana")

    # Novo processo: outro agente, mesmo arquivo SQLite.
    model = ScriptedChatModel(responses=[AIMessage("Claro, Ana!")])
    second_run = _agent(tmp_path, repo)
    second_run.model = model
    resumed = second_run.new_session("cliente-ana")
    assert len(resumed.history()) == 2
    resumed.send("Lembra de mim?")
    assert any("Ana" in str(m.content) for m in model.received[0])


def test_list_sessions(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo, AIMessage("a"), AIMessage("b"), AIMessage("c"))
    agent.new_session("s-1").send("oi")
    s2 = agent.new_session("s-2")
    s2.send("oi")
    s2.send("tudo bem?")
    sessions = {s.thread_id: s for s in list_sessions(agent.checkpointer)}
    assert set(sessions) == {"s-1", "s-2"}
    assert sessions["s-2"].messages == 4
    assert sessions["s-2"].updated_at.tzinfo is not None


def test_forget_deletes_history(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo, AIMessage("Oi!"))
    session = agent.new_session("apagar")
    session.send("meu email é ana@x.com")
    session.forget()
    assert agent.new_session("apagar").history() == []
    assert "apagar" not in {s.thread_id for s in list_sessions(agent.checkpointer)}


def test_escalation_through_graph_uses_session_id(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(
        tmp_path, repo,
        tool_call("escalate_to_human", {"reason": "reclamacao", **CASE}),
        AIMessage("Registrei seu caso no protocolo ATD-00001."),
    )
    reply = agent.new_session("reclamacao-1").send("Quero reclamar, meu violão veio trincado")
    assert '"ticket":"ATD-00001"' in reply.tool_calls[0].output
    ticket = agent.handoffs.list()[0]
    assert ticket.session_id == "reclamacao-1" and ticket.order_id == 7


# --- Verificação de protocolos ----------------------------------------------------------

from langchain_core.messages import HumanMessage, ToolMessage  # noqa: E402

from emporio.agent.graph import FALLBACK_UNGROUNDED_TICKET  # noqa: E402
from emporio.agent.verification import ungrounded_protocols  # noqa: E402

ISSUED = [ToolMessage('{"status":"created","ticket":"ATD-00001"}', tool_call_id="t1", name="escalate_to_human")]


@pytest.mark.parametrize(
    ("text", "history", "expected"),
    [
        ("Seu protocolo é: #ESCALATE-7-DEFEITO-LETICIA", [], {"ESCALATE-7-DEFEITO-LETICIA"}),
        ("Protocolo nº 12345", [], {"12345"}),
        ("Seu protocolo é ATD-00099", ISSUED, {"ATD-00099"}),
        ("Registrei no protocolo ATD-00001.", ISSUED, set()),
        ("Para gerar um protocolo, preciso do seu contato.", [], set()),
        ("Vou te passar o protocolo e o prazo.", [], set()),
    ],
)
def test_ungrounded_protocols(text: str, history: list, expected: set[str]) -> None:
    assert ungrounded_protocols(text, history) == expected


def test_invented_protocol_is_corrected(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(
        tmp_path, repo,
        AIMessage("Registrei! Seu protocolo é #ESCALATE-7."),  # inventado
        tool_call("escalate_to_human", {"reason": "defeito", **CASE}),  # correção: chama a ferramenta
        AIMessage("Pronto, protocolo ATD-00001."),
    )
    reply = agent.new_session().send("meu violão veio trincado, registra pra mim")
    assert reply.text == "Pronto, protocolo ATD-00001." and not reply.error
    assert len(agent.handoffs.list()) == 1
    retry_input = agent.model.received[1]
    assert isinstance(retry_input[-1], HumanMessage) and "Verificação automática" in retry_input[-1].content


def test_correction_is_not_saved_in_history(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo, AIMessage("Protocolo: XYZ-1"), AIMessage("Vou encaminhar, me passa seu contato?"))
    session = agent.new_session()
    session.send("quero reclamar")
    assert not any("Verificação automática" in str(m.content) for m in session.history())


def test_insisting_on_invented_protocol_returns_safe_message(tmp_path: Path, repo: StoreRepository) -> None:
    agent = _agent(tmp_path, repo, AIMessage("Protocolo: XYZ-1"), AIMessage("Protocolo: XYZ-2"))
    reply = agent.new_session().send("quero reclamar")
    assert reply.text == FALLBACK_UNGROUNDED_TICKET
