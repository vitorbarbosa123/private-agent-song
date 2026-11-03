"""Testes do relógio e do horário de funcionamento."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from emporio.business_hours import STORE_TZ, easter, holiday_name, make_clock, store_status_at
from emporio.config import Settings


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=STORE_TZ)


@pytest.mark.parametrize(("year", "expected"), [(2025, date(2025, 4, 20)), (2026, date(2026, 4, 5))])
def test_easter(year: int, expected: date) -> None:
    assert easter(year) == expected


def test_holidays() -> None:
    assert holiday_name(date(2026, 4, 3)) == "Sexta-feira Santa"
    assert holiday_name(date(2026, 8, 26)) == "Aniversário de Campo Grande"
    assert holiday_name(date(2026, 11, 20)) == "Dia Nacional de Zumbi e da Consciência Negra"
    assert holiday_name(date(2026, 3, 2)) is None


@pytest.mark.parametrize(
    ("moment", "is_open"),
    [
        ("2026-03-02T08:59", False),  # segunda, antes de abrir
        ("2026-03-02T09:00", True),
        ("2026-03-02T17:59", True),
        ("2026-03-02T18:00", False),  # fecha às 18h
        ("2026-03-07T12:30", True),  # sábado
        ("2026-03-07T13:00", False),  # sábado fecha às 13h
        ("2026-03-08T10:00", False),  # domingo
        ("2026-04-03T10:00", False),  # Sexta-feira Santa
    ],
)
def test_is_open(moment: str, is_open: bool) -> None:
    assert store_status_at(at(moment)).is_open is is_open


def test_next_opening_skips_sunday() -> None:
    status = store_status_at(at("2026-03-07T14:00"))  # sábado à tarde
    assert status.next_opening == at("2026-03-09T09:00")  # segunda


def test_next_opening_skips_holiday() -> None:
    status = store_status_at(at("2026-04-02T19:00"))  # quinta à noite; sexta é feriado
    assert status.next_opening == at("2026-04-04T09:00")  # sábado


def test_fixed_clock_from_settings() -> None:
    clock = make_clock(Settings(_env_file=None, EMPORIO_NOW="2026-03-02T10:30"))
    assert clock() == at("2026-03-02T10:30")
    assert clock().tzinfo == STORE_TZ


def test_real_clock_uses_store_timezone() -> None:
    clock = make_clock(Settings(_env_file=None))
    assert clock().tzinfo == STORE_TZ
