"""Ferramenta de encaminhamento para a equipe humana."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from emporio.business_hours import describe_moment, store_status_at
from emporio.policy_rules import STORE_INFO
from emporio.tools.context import ToolContext

HandoffReason = Literal[
    "reclamacao", "defeito", "cancelamento", "troca_ou_devolucao",
    "pedido_do_cliente", "sem_resposta", "outro",
]


class EscalateInput(BaseModel):
    reason: HandoffReason = Field(
        description="reclamacao | defeito | cancelamento | troca_ou_devolucao | pedido_do_cliente "
        "(cliente pediu uma pessoa) | sem_resposta (você não soube responder) | outro"
    )
    summary: str = Field(
        min_length=15,
        description="Resumo objetivo para a equipe: o que o cliente quer, produto/pedido, o que já foi "
        "verificado. A equipe não vai reler a conversa.",
    )
    customer_name: str | None = Field(default=None, description="Nome do cliente, se informado.")
    contact: str | None = Field(default=None, description="Telefone ou e-mail para retorno.")
    order_id: int | None = Field(default=None, description="Número do pedido relacionado, se houver.")


class EscalateResult(BaseModel):
    status: Literal["created", "already_open", "contact_required"]
    ticket: str | None = None
    team_available_now: bool | None = None
    expected_response: str | None = None
    notes: list[str] = Field(default_factory=list)


def escalate_to_human(ctx: ToolContext, args: EscalateInput) -> EscalateResult:
    if ctx.handoffs is None:
        raise RuntimeError("Registro de atendimentos indisponível neste contexto.")
    if not args.contact:
        return EscalateResult(
            status="contact_required",
            notes=["Antes de encaminhar, peça ao cliente o nome e um telefone ou e-mail para retorno."],
        )

    existing = ctx.handoffs.find_open(ctx.session_id, args.reason)
    if existing:
        return EscalateResult(
            status="already_open",
            ticket=existing.code,
            notes=["Já existe um atendimento aberto para este assunto nesta conversa; informe o mesmo protocolo."],
        )

    now = ctx.clock()
    ticket = ctx.handoffs.create(
        session_id=ctx.session_id, reason=args.reason, summary=args.summary,
        customer_name=args.customer_name, contact=args.contact, order_id=args.order_id, now=now,
    )
    status = store_status_at(now)
    if args.reason == "reclamacao":
        expected = "retorno em até 24 horas úteis (manual, seção 7.3)"
    elif status.is_open:
        expected = "a equipe entra em contato ainda hoje, durante o expediente"
    else:
        when = describe_moment(status.next_opening, now) if status.next_opening else "no próximo dia útil"
        expected = f"a equipe entra em contato a partir de {when}"
    return EscalateResult(
        status="created",
        ticket=ticket.code,
        team_available_now=status.is_open,
        expected_response=expected,
        notes=[
            "Informe o protocolo e o prazo ao cliente. Não prometa solução: quem decide é a equipe.",
            f"Se o cliente preferir, ele também pode chamar no WhatsApp {STORE_INFO['phone_whatsapp']}.",
        ],
    )
