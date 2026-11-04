"""Testes da observabilidade (sem Langfuse no ar)."""

from __future__ import annotations

from emporio.agent import AgentReply
from emporio.config import Settings
from emporio.observability import Tracer, mask_personal_data


def test_mask_personal_data_in_nested_structures() -> None:
    data = {
        "messages": [
            "Meu email é ana@x.com e o tel (67) 99654-7821",
            {"content": "cartão 4111 1111 1111 1111, cvv 123, cpf 123.456.789-09"},
        ],
        "order_id": 8,
    }
    masked = mask_personal_data(data)
    text = str(masked)
    for secret in ("ana@x.com", "99654-7821", "4111 1111", "cvv 123", "123.456.789-09"):
        assert secret not in text
    assert masked["order_id"] == 8  # números que não são dados pessoais ficam
    assert "[e-mail]" in text and "[telefone]" in text and "[cpf]" in text


def test_mask_keeps_prices_and_tracking_codes() -> None:
    text = "R$ 2.199,00, pedido 8, rastreio BRJL5544332BR, protocolo ATD-00001"
    assert mask_personal_data(text) == text


def test_tracer_is_disabled_without_keys() -> None:
    tracer = Tracer(Settings(_env_file=None))
    assert not tracer.enabled
    with tracer.turn(session_id="s", model="m", metadata={}) as callbacks:
        assert callbacks == []
    tracer.record(AgentReply("ok"), guard_flags=[], verification_issues=[])  # no-op, sem erro
    tracer.flush()
