"""Testes da avaliação de ponta a ponta (lógica de verificação e conjuntos de dados, sem rede)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import AIMessage

from emporio.agent import AgentReply
from emporio.agent.graph import ToolCallRecord
from emporio.evals.agent_eval import (
    CALIBRATION,
    Expect,
    JudgeVerdict,
    ScenarioResult,
    TurnResult,
    check_turn,
    load_scenarios,
    run_scenario,
    summarize,
    tool_expectations_met,
)
from emporio.repository import StoreRepository
from tests.test_agent import tool_call
from tests.test_memory_handoff import _agent


def reply(text: str, *tools: str, error: bool = False) -> AgentReply:
    return AgentReply(text, [ToolCallRecord(t, {}, "") for t in tools], error)


# --- Conjuntos de dados ----------------------------------------------------------------------


def test_scenarios_are_valid() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) >= 25
    assert all(s.turns for s in scenarios)
    assert any(s.category == "seguranca" for s in scenarios)


def test_unknown_expectation_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump({"scenarios": [{
        "id": "x", "category": "c", "goal": "g", "now": "2026-03-02T10:30",
        "turns": [{"user": "oi", "expect": {"contains_any_2": ["a"]}}],
    }]}))
    with pytest.raises(ValueError):
        load_scenarios(path)


def test_unknown_tool_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump({"scenarios": [{
        "id": "x", "category": "c", "goal": "g", "now": "2026-03-02T10:30",
        "turns": [{"user": "oi", "expect": {"tools": ["buscar_tudo"]}}],
    }]}))
    with pytest.raises(ValueError, match="desconhecidas"):
        load_scenarios(path)


def test_calibration_set_is_balanced() -> None:
    cases = yaml.safe_load(CALIBRATION.read_text(encoding="utf-8"))["cases"]
    expected = [c["expected"] for c in cases]
    assert set(expected) == {"pass", "fail"} and expected.count("fail") >= 5


# --- Verificações determinísticas ---------------------------------------------------------------


def test_check_turn_passes() -> None:
    expect = Expect(tools=["get_product_details"], contains=["2.199,00"], not_contains=["12%"])
    assert check_turn(expect, reply("Custa R$ 2.199,00", "get_product_details")) == []


@pytest.mark.parametrize(
    ("expect", "agent_reply", "fragment"),
    [
        (Expect(tools=["search_products"]), reply("ok"), "não chamou"),
        (Expect(tools_any=["a", "b"]), reply("ok", "c"), "nenhuma de"),
        (Expect(forbidden_tools=["get_order_status"]), reply("ok", "get_order_status"), "proibida"),
        (Expect(no_tools=True), reply("ok", "list_categories"), "não deveria"),
        (Expect(contains=["Violão"]), reply("guitarra"), "faltou"),
        (Expect(not_contains=["4111"]), reply("cartão 4111"), "proibido"),
    ],
)
def test_check_turn_failures(expect: Expect, agent_reply: AgentReply, fragment: str) -> None:
    failures = check_turn(expect, agent_reply)
    assert failures and fragment in failures[0]


def test_text_comparison_ignores_accents_and_case() -> None:
    assert check_turn(Expect(contains=["NÃO ENVIE"]), reply("por favor, nao envie")) == []


def test_contains_any_groups() -> None:
    expect = Expect(contains_any=[["fechad"], ["feriado", "sexta-feira santa"]])
    assert check_turn(expect, reply("Hoje é Sexta-feira Santa e estamos fechados")) == []
    assert check_turn(expect, reply("Estamos fechados")) == ["faltou um de ['feriado', 'sexta-feira santa']"]


def test_error_reply_always_fails() -> None:
    assert check_turn(None, reply("Poxa, tive um problema", error=True))


def test_tool_accuracy_only_counts_tool_expectations() -> None:
    assert tool_expectations_met(Expect(contains=["x"]), reply("x")) is None
    assert tool_expectations_met(Expect(tools=["a"]), reply("sem x", "a")) is True  # texto não conta
    assert tool_expectations_met(Expect(tools=["a"]), reply("x")) is False


# --- Execução e resumo ---------------------------------------------------------------------------


def test_run_scenario_with_scripted_agent(tmp_path: Path, repo: StoreRepository) -> None:
    scenario = load_scenarios()[0]  # catalogo_violoes_ate_1000
    agent = _agent(
        tmp_path, repo,
        tool_call("search_products", {"category": "violão", "max_price": 1000}),
        AIMessage("Temos o Tagima Memphis AC-39 por R$ 429,90!"),
    )
    result = run_scenario(scenario, lambda now: agent)
    assert result.checks_passed and result.turns[0].tools == ["search_products"]


def _turn(failures: list[str], tools_ok: bool | None, cost: float | None = 0.01) -> TurnResult:
    return TurnResult("u", "r", [], [], failures, tools_ok, 1.0, 100, 10, cost)


def test_summarize() -> None:
    good = ScenarioResult("a", "preco", [_turn([], True)],
                          judge=JudgeVerdict(tone=5, policy_adherence=5, helpfulness=5, issues="").model_dump())
    bad_judge = ScenarioResult("b", "preco", [_turn([], None)],
                               judge=JudgeVerdict(tone=5, policy_adherence=2, helpfulness=4, issues="x").model_dump())
    bad_check = ScenarioResult("c", "seguranca", [_turn(["faltou x"], False)])
    summary = summarize([good, bad_judge, bad_check])
    assert summary.passed == 1 and summary.checks_passed == 2
    assert summary.tool_accuracy == 0.5
    assert summary.by_category == {"preco": (1, 2), "seguranca": (0, 1)}
    assert summary.total_cost_usd == 0.03 and summary.total_tokens == 330


def test_scenario_now_is_timezone_naive_and_parsed() -> None:
    assert all(isinstance(s.now, datetime) for s in load_scenarios())
