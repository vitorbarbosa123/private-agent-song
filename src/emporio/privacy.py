"""Detecção e remoção de dados de pagamento (cartão e CVV).

Módulo neutro, sem dependências do agente: usado pelo guardrail de entrada
(`emporio.agent.guards`) e pela máscara do rastreamento (`emporio.observability`).
"""

from __future__ import annotations

import re

_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ .-]?){13,19}(?!\d)")
_CVV = re.compile(r"\b(cvv|cvc|codigo de seguranca)\b\D{0,10}\d{3,4}\b", re.IGNORECASE)


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, char in enumerate(reversed(digits)):
        n = int(char)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _mask_cards(text: str) -> tuple[str, bool]:
    found = False

    def replace(match: re.Match[str]) -> str:
        nonlocal found
        digits = re.sub(r"\D", "", match.group())
        # 14-19 dígitos + Luhn: evita confundir com telefones (até 13 dígitos com +55).
        if 14 <= len(digits) <= 19 and luhn_valid(digits):
            found = True
            return f"[cartão final {digits[-4:]} removido]"
        return match.group()

    return _CARD_CANDIDATE.sub(replace, text), found


def mask_card_numbers(text: str) -> str:
    """Remove números de cartão (também usado pela máscara do rastreamento)."""
    masked, _ = _mask_cards(text)
    return _CVV.sub("[código de segurança removido]", masked)
