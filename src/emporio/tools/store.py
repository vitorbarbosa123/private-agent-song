"""Ferramenta de horário: a loja está aberta agora? Quando abre?"""

from __future__ import annotations

from pydantic import BaseModel

from emporio.business_hours import WEEKDAY_NAMES, describe_moment, store_status_at
from emporio.tools.context import ToolContext
from emporio.tools.products import NoInput


class StoreStatusResult(BaseModel):
    now: str
    is_open: bool
    today: str
    closes_at: str | None = None
    next_opening: str | None = None
    weekly_hours: list[str]
    notes: list[str]


def store_status(ctx: ToolContext, _: NoInput | None = None) -> StoreStatusResult:
    now = ctx.clock()
    status = store_status_at(now)
    if status.holiday:
        today = f"feriado ({status.holiday}): fechado"
    elif status.today_hours:
        opening, closing = status.today_hours
        today = f"{opening:%H:%M} às {closing:%H:%M}"
    else:
        today = "fechado"
    return StoreStatusResult(
        now=f"{WEEKDAY_NAMES[now.weekday()]}, {now:%d/%m/%Y %H:%M}",
        is_open=status.is_open,
        today=today,
        closes_at=f"{status.closes_at:%H:%M}" if status.closes_at else None,
        next_opening=describe_moment(status.next_opening, now) if status.next_opening else None,
        weekly_hours=[
            "Segunda a sexta: 09:00 às 18:00",
            "Sábado: 09:00 às 13:00",
            "Domingos e feriados: fechado",
        ],
        notes=[
            "O WhatsApp segue o mesmo horário. Fora do expediente, informe quando a equipe retorna.",
            "Em datas especiais (Black Friday, aniversário da loja, Natal) o horário pode ser "
            "estendido; a loja avisa nas redes sociais.",
        ],
    )
