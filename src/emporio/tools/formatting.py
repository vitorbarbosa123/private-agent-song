"""Formatação de valores para o LLM.

As ferramentas devolvem valores já formatados ("R$ 2.199,00", "15/02/2026") para que o
modelo apenas os repita: contas e formatação feitas pelo LLM são fonte de alucinação.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from emporio.data.utils import format_brl


def brl(value: float | Decimal) -> str:
    return format_brl(float(value))


def br_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def percent(value: float) -> str:
    return f"{value:g}%"
