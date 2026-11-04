"""Ferramentas de pedidos: status/rastreio e elegibilidade de troca ou devolução.

Ambas exigem verificação de identidade (número do pedido + e-mail ou telefone do titular)
e contam as tentativas com dados que não conferem: após `MAX_AUTH_ATTEMPTS` falhas na
mesma conversa, a consulta é bloqueada e o cliente deve ser encaminhado a um atendente.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from emporio import policy_rules as rules
from emporio.repository.models import Order
from emporio.tools.context import ToolContext
from emporio.tools.formatting import br_date, brl

AuthStatus = Literal["ok", "verification_required", "not_verified", "blocked"]

_PAYMENT_LABELS = {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto bancário"}


class OrderCredentials(BaseModel):
    order_id: int = Field(description="Número do pedido informado pelo cliente.")
    email: str | None = Field(default=None, description="E-mail do titular do pedido.")
    phone: str | None = Field(default=None, description="Telefone do titular, em qualquer formato.")


def _authenticate(ctx: ToolContext, creds: OrderCredentials) -> tuple[AuthStatus, Order | None, str]:
    if ctx.auth_locked:
        return "blocked", None, (
            "Limite de tentativas de verificação atingido nesta conversa. Não tente novamente. "
            "Ofereça registrar o caso para a equipe verificar com escalate_to_human (peça nome e "
            "um telefone ou e-mail para retorno)."
        )
    if not creds.email and not creds.phone:
        return "verification_required", None, (
            "Para proteger os dados do cliente, peça o e-mail ou o telefone cadastrado no pedido "
            "antes de consultar."
        )
    order = ctx.repo.get_order(creds.order_id, email=creds.email, phone=creds.phone)
    if order is None:
        ctx.failed_auth_attempts += 1
        left = max(0, ctx.max_auth_attempts - ctx.failed_auth_attempts)
        return "not_verified", None, (
            "Não foi possível localizar um pedido com esse número e esses dados. Peça ao cliente "
            f"para conferir o número do pedido e o contato cadastrado ({left} tentativa(s) restante(s)). "
            "Não diga se o pedido existe. Se o cliente não tiver esses dados em mãos ou estiver "
            "relatando defeito ou reclamação, ofereça também registrar o caso para a equipe com "
            "escalate_to_human (peça nome e contato; no resumo, cite só o número que ele informou)."
        )
    return "ok", order, ""


# --- get_order_status ---------------------------------------------------------------


class OrderView(BaseModel):
    order_id: int
    customer_first_name: str
    order_date: str
    status: str
    items: list[str]
    total: str
    payment: str
    tracking_code: str | None = None
    tracking_info: str | None = None
    estimated_delivery: str | None = None
    notes: list[str] = Field(default_factory=list)


class OrderStatusResult(BaseModel):
    status: AuthStatus
    message: str | None = None
    order: OrderView | None = None


def describe_payment(order: Order) -> str:
    if order.payment_type == "credit":
        if order.installments and order.installments > 1 and order.installment_value_brl:
            return f"cartão de crédito em {order.installments}x de {brl(order.installment_value_brl)}"
        return "cartão de crédito à vista"
    return _PAYMENT_LABELS.get(order.payment_type or "", order.payment_type or "não informado")


def order_view(order: Order, today: date) -> OrderView:
    notes: list[str] = []
    tracking_info = None
    if order.status == "pending":
        if order.payment_type == "boleto":
            notes.append("Aguardando a compensação do boleto, que leva até 3 dias úteis.")
        else:
            notes.append("Aguardando a confirmação do pagamento.")
    elif order.status == "confirmed":
        notes.append("O código de rastreio é enviado por e-mail e WhatsApp assim que o pedido for despachado.")
    elif order.status == "shipped":
        tracking_info = "Rastreie no site dos Correios ou da Jadlog com o código informado."
        if order.estimated_delivery and today > order.estimated_delivery:
            notes.append(
                f"A previsão de entrega ({br_date(order.estimated_delivery)}) já passou. Primeiro informe "
                "o status e o código de rastreio; depois peça desculpas e PERGUNTE se o cliente quer que "
                "você encaminhe o caso para a equipe verificar com a transportadora."
            )
    elif order.status == "cancelled":
        notes.append(f"Motivo do cancelamento: {order.notes}" if order.notes else "Pedido cancelado.")

    return OrderView(
        order_id=order.order_id,
        customer_first_name=order.customer_first_name,
        order_date=br_date(order.order_date),
        status=order.status_label,
        items=[f"{i.quantity}x {i.product_name}" for i in order.items],
        total=brl(order.total_brl),
        payment=describe_payment(order),
        tracking_code=order.tracking_code,
        tracking_info=tracking_info,
        estimated_delivery=br_date(order.estimated_delivery) if order.estimated_delivery else None,
        notes=notes,
    )


def get_order_status(ctx: ToolContext, args: OrderCredentials) -> OrderStatusResult:
    status, order, message = _authenticate(ctx, args)
    if order is None:
        return OrderStatusResult(status=status, message=message)
    return OrderStatusResult(status="ok", order=order_view(order, ctx.clock().date()))


# --- check_return_eligibility -------------------------------------------------------

ReturnReason = Literal["arrependimento", "defeito", "troca_preferencia"]

_COMMON_EXCLUSIONS = [
    "Não são elegíveis: instrumentos com personalização ou ajuste sob encomenda (setup, "
    "regulagem especial), itens de liquidação com aviso de 'venda final' e boquilhas de "
    "instrumentos de sopro (manual 4.4).",
]


class ReturnEligibilityInput(OrderCredentials):
    reason: ReturnReason = Field(
        description="'arrependimento' (desistência sem motivo), 'defeito' (defeito de fabricação) "
        "ou 'troca_preferencia' (trocar cor/modelo/tamanho)."
    )
    received_date: date | None = Field(
        default=None, description="Data em que o cliente recebeu o produto (AAAA-MM-DD), se ele informar."
    )


class ReturnEligibilityResult(BaseModel):
    status: AuthStatus
    message: str | None = None
    eligible: bool | None = None
    decision: str | None = None
    deadline: str | None = None
    days_remaining: int | None = Field(
        default=None, description="Dias corridos até o fim do prazo (0 = vence hoje). Use este valor; não calcule."
    )
    days_elapsed: int | None = None
    date_basis: str | None = None
    conditions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    policy_sections: list[str] = Field(default_factory=list)
    requires_human: bool = False
    notes: list[str] = Field(default_factory=list)


def check_return_eligibility(ctx: ToolContext, args: ReturnEligibilityInput) -> ReturnEligibilityResult:
    status, order, message = _authenticate(ctx, args)
    if order is None:
        # Defeito não pode ficar sem saída por falta de dados do pedido: a equipe resolve.
        needs_human = status == "blocked" or (status == "not_verified" and args.reason == "defeito")
        return ReturnEligibilityResult(status=status, message=message, requires_human=needs_human)

    today = ctx.clock().date()
    result = ReturnEligibilityResult(status="ok", policy_sections=["4"])

    if order.status == "cancelled":
        result.eligible = False
        result.decision = "O pedido foi cancelado; não há produto a devolver."
        return result
    if order.status in {"pending", "confirmed"}:
        result.eligible = None
        result.decision = ("O pedido ainda não foi enviado. Para desistir da compra, o caminho é o "
                           "cancelamento, que precisa ser feito por um atendente.")
        result.requires_human = True
        result.next_steps = ["Encaminhar para um atendente solicitar o cancelamento."]
        return result
    if order.status == "shipped" and args.received_date is None:
        result.eligible = None
        result.decision = ("O pedido ainda consta como em trânsito. Os prazos contam a partir do "
                           "recebimento. Se o produto chegar com avaria, o cliente deve recusar a entrega.")
        result.policy_sections = ["4.1", "5.2"]
        return result

    # Data de recebimento: informada pelo cliente ou, na falta dela, a previsão de entrega.
    if args.received_date is not None:
        received, basis = args.received_date, "data de recebimento informada pelo cliente"
    elif order.estimated_delivery is not None:
        received, basis = order.estimated_delivery, "previsão de entrega do pedido (data real não registrada)"
    else:
        received, basis = order.order_date, "data do pedido (sem previsão de entrega registrada)"
    if received < order.order_date or received > today:
        result.eligible = None
        result.decision = "A data de recebimento informada é inconsistente. Confirme a data com o cliente."
        return result

    days_since_receipt = (today - received).days
    result.date_basis = f"{basis}: {br_date(received)}"
    if args.received_date is None and order.estimated_delivery is not None:
        result.notes.append(
            "A data usada é a PREVISÃO de entrega, não a data real. Diga isso ao cliente (ex.: 'pela "
            "previsão de entrega, dia 17/02') e, se ele recebeu em outra data, consulte de novo com received_date."
        )

    if args.reason in {"arrependimento", "troca_preferencia"}:
        limit = rules.WITHDRAWAL_DAYS if args.reason == "arrependimento" else rules.PREFERENCE_EXCHANGE_DAYS
        deadline = received + timedelta(days=limit)
        result.days_elapsed = days_since_receipt
        result.deadline = br_date(deadline)
        result.eligible = today <= deadline
        result.days_remaining = (deadline - today).days if result.eligible else None
        result.conditions = [
            "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
            *_COMMON_EXCLUSIONS,
        ]
        if args.reason == "arrependimento":
            result.policy_sections = ["4.1", "4.4"]
            if result.eligible:
                result.decision = f"Dentro do prazo de {limit} dias corridos do direito de arrependimento."
                result.next_steps = [
                    "Informe ao cliente o prazo, as condições, que o frete de devolução é por conta da "
                    "loja e que o reembolso sai na mesma forma de pagamento em até 10 dias úteis.",
                    "Depois PERGUNTE se ele quer que você encaminhe à equipe (escalate_to_human) para "
                    "gerar a autorização de devolução.",
                ]
                result.requires_human = True
            else:
                result.decision = (f"O prazo de {limit} dias corridos para arrependimento terminou em "
                                   f"{br_date(deadline)}. Se houver defeito, verifique a garantia.")
        else:
            result.policy_sections = ["4.3", "4.4"]
            result.conditions.append("Sujeito à disponibilidade do produto desejado; diferenças de valor "
                                     "são cobradas ou reembolsadas.")
            if result.eligible:
                result.decision = f"Dentro do prazo de {limit} dias para troca por preferência."
                result.next_steps = ["Verifique a disponibilidade do produto desejado.",
                                     "Informe prazo e condições e PERGUNTE se o cliente quer que você "
                                     "encaminhe à equipe (escalate_to_human) para concluir a troca."]
                result.requires_human = True
            else:
                result.decision = f"O prazo de {limit} dias para troca por preferência terminou em {br_date(deadline)}."
        return result

    # Defeito: troca direta em 30 dias da compra; garantia legal em 90 dias do recebimento.
    days_since_purchase = (today - order.order_date).days
    store_deadline = order.order_date + timedelta(days=rules.DEFECT_EXCHANGE_DAYS)
    legal_deadline = received + timedelta(days=rules.LEGAL_WARRANTY_DAYS)
    result.days_elapsed = days_since_purchase
    result.requires_human = True
    result.policy_sections = ["4.2", "8"]
    result.conditions = [
        "Não cobre mau uso, quedas, umidade excessiva, modificações não autorizadas, desgaste "
        "natural (trastes, cordas, feltros) nem danos apenas estéticos.",
    ]
    if today <= store_deadline:
        result.eligible = True
        result.deadline = br_date(store_deadline)
        result.days_remaining = (store_deadline - today).days
        result.decision = f"Dentro de {rules.DEFECT_EXCHANGE_DAYS} dias da compra: troca direta na loja."
    elif today <= legal_deadline:
        result.eligible = True
        result.deadline = br_date(legal_deadline)
        result.days_remaining = (legal_deadline - today).days
        result.decision = (f"Fora dos {rules.DEFECT_EXCHANGE_DAYS} dias de troca direta, mas dentro da "
                           f"garantia legal de {rules.LEGAL_WARRANTY_DAYS} dias: a loja intermedia o "
                           "reparo ou troca com o fabricante.")
    else:
        result.eligible = False
        result.decision = ("Fora da garantia legal. Verifique a garantia do fabricante (de 6 meses a 2 "
                           "anos, conforme o certificado do produto); a loja pode intermediar.")
    result.next_steps = [
        "Informe a situação (prazo e cobertura) e peça fotos ou vídeo do defeito.",
        "Com a concordância do cliente, registre com escalate_to_human (reason='defeito'), "
        "incluindo este resultado no resumo.",
    ]
    return result
