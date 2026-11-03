"""Relógio da loja e horário de funcionamento (manual, seção 2).

- Segunda a sexta: 09:00-18:00; sábado: 09:00-13:00; domingos e feriados: fechado.
- Feriados considerados: nacionais (incluindo Sexta-feira Santa, móvel), estadual de MS
  (11/10) e municipal de Campo Grande (26/08). Datas especiais com horário estendido
  (Black Friday, Natal) são comunicadas pela loja e não são previsíveis aqui.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from emporio.config import Settings

STORE_TZ = ZoneInfo("America/Campo_Grande")

# weekday() -> (abertura, fechamento); domingo (6) ausente = fechado.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    **{d: (time(9), time(18)) for d in range(5)},
    5: (time(9), time(13)),
}
WEEKDAY_NAMES = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                 "sexta-feira", "sábado", "domingo")

_FIXED_HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (8, 26): "Aniversário de Campo Grande",
    (9, 7): "Independência do Brasil",
    (10, 11): "Criação do Estado de Mato Grosso do Sul",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
    (12, 25): "Natal",
}

Clock = Callable[[], datetime]


def make_clock(settings: Settings) -> Clock:
    """Relógio no fuso da loja. EMPORIO_NOW fixa o horário (demonstrações e testes)."""
    fixed = settings.emporio_now
    if fixed is None:
        return lambda: datetime.now(STORE_TZ)
    fixed = fixed.replace(tzinfo=STORE_TZ) if fixed.tzinfo is None else fixed.astimezone(STORE_TZ)
    return lambda: fixed


def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def holiday_name(day: date) -> str | None:
    if name := _FIXED_HOLIDAYS.get((day.month, day.day)):
        return name
    if day == easter(day.year) - timedelta(days=2):
        return "Sexta-feira Santa"
    return None


def hours_for(day: date) -> tuple[time, time] | None:
    if holiday_name(day):
        return None
    return OPENING_HOURS.get(day.weekday())


@dataclass(frozen=True)
class StoreStatus:
    now: datetime
    is_open: bool
    today_hours: tuple[time, time] | None
    holiday: str | None
    closes_at: datetime | None
    next_opening: datetime | None


def store_status_at(now: datetime) -> StoreStatus:
    today = now.date()
    hours = hours_for(today)
    is_open = hours is not None and hours[0] <= now.time() < hours[1]
    closes_at = datetime.combine(today, hours[1], STORE_TZ) if is_open and hours else None

    next_opening = None
    if not is_open:
        for offset in range(0, 15):
            day = today + timedelta(days=offset)
            day_hours = hours_for(day)
            if day_hours is None:
                continue
            opening = datetime.combine(day, day_hours[0], STORE_TZ)
            if opening > now:
                next_opening = opening
                break
    return StoreStatus(now, is_open, hours, holiday_name(today), closes_at, next_opening)


def describe_moment(moment: datetime, now: datetime) -> str:
    """'hoje às 09:00', 'amanhã às 09:00' ou 'segunda-feira (09/03) às 09:00'."""
    delta = (moment.date() - now.date()).days
    hour = moment.strftime("%H:%M")
    if delta == 0:
        return f"hoje às {hour}"
    if delta == 1:
        return f"amanhã às {hour}"
    return f"{WEEKDAY_NAMES[moment.weekday()]} ({moment.strftime('%d/%m')}) às {hour}"
