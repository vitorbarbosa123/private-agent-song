"""Verificação determinística das respostas antes de chegarem ao cliente.

Motivação (encontrada em teste real): o modelo disse "vou registrar seu caso", não chamou
a ferramenta e inventou um protocolo ("#ESCALATE-7-DEFEITO-LETICIA"). Instruções no prompt
reduzem, mas não eliminam esse tipo de alucinação; por isso conferimos a resposta contra os
resultados das ferramentas presentes no histórico.

Regras:
- todo código de protocolo citado precisa ter sido devolvido por `escalate_to_human`;
- todo valor em R$ citado precisa ter vindo de uma ferramenta, do próprio cliente ou dos
  valores fixos da política (frete grátis a partir de R$ 500 etc.). Contas feitas pelo
  modelo são sinalizadas: totais e parcelas vêm de `payment_options`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage

from emporio import policy_rules
from emporio.data.utils import normalize_for_search

TICKET_CODE = re.compile(r"\bATD-\d{5}\b")
# "protocolo: X", "protocolo é X", "protocolo nº X", "protocolo #X"...
_PROTOCOL_MENTION = re.compile(
    r"protocolo\W{0,6}(?:e|eh|n[o°º]?\.?|numero|de numero|:)?\W{0,6}(#?[a-z0-9][a-z0-9-]{3,})",
)


def issued_tickets(messages: list[AnyMessage]) -> set[str]:
    """Protocolos efetivamente criados por ferramentas nesta conversa."""
    codes: set[str] = set()
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "escalate_to_human":
            codes.update(TICKET_CODE.findall(str(message.content)))
    return codes


def ungrounded_protocols(text: str, messages: list[AnyMessage]) -> set[str]:
    """Códigos de protocolo citados na resposta que nenhuma ferramenta emitiu."""
    known = issued_tickets(messages)
    cited = set(TICKET_CODE.findall(text))
    # Menções do tipo "protocolo: XYZ-123" com um código que não segue o padrão ATD-NNNNN.
    for token in _PROTOCOL_MENTION.findall(normalize_for_search(text)):
        token = token.lstrip("#").upper()
        if any(ch.isdigit() for ch in token) or "-" in token:
            cited.add(token)
    return {code for code in cited if code not in known}


# --- Preços ------------------------------------------------------------------------------

# "R$ 2.199,00", "R$2199", "R$ 1.000", "R$ 35"
_BRL = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")

# Valores fixos da política que o modelo pode citar sem consultar ferramenta.
POLICY_AMOUNTS: frozenset[Decimal] = frozenset({
    policy_rules.FREE_SHIPPING_THRESHOLD,
    policy_rules.METRO_SHIPPING_FEE,
    policy_rules.SPLIT_PAYMENT_MIN_TOTAL,
    *(value for _, value in policy_rules.INSTALLMENT_TIERS),
})


def parse_brl(raw: str) -> Decimal:
    return Decimal(raw.replace(".", "").replace(",", ".")).quantize(Decimal("0.01"))


def amounts_in(text: str) -> set[Decimal]:
    return {parse_brl(m) for m in _BRL.findall(text)}


def ungrounded_prices(text: str, messages: list[AnyMessage]) -> set[Decimal]:
    """Valores em R$ citados na resposta que não vieram de ferramenta, do cliente ou da política.

    O cliente pode ter citado um valor ("até R$ 1000") e o modelo pode repeti-lo; contas
    feitas pelo próprio modelo (somas, diferenças, parcelas) são sinalizadas, porque devem
    vir de payment_options/shipping_quote.
    """
    known = set(POLICY_AMOUNTS)
    for message in messages:
        if isinstance(message, (ToolMessage, HumanMessage)):
            known |= amounts_in(str(message.content))
    return amounts_in(text) - known


# --- Verificação consolidada ----------------------------------------------------------------


@dataclass(frozen=True)
class ReplyIssue:
    kind: Literal["ticket", "price"]
    values: tuple[str, ...]

    def describe(self) -> str:
        values = ", ".join(self.values)
        if self.kind == "ticket":
            return (f"cita protocolo(s) {values} que não foram emitidos por escalate_to_human. Se for "
                    "registrar o caso, chame escalate_to_human agora; caso contrário, não cite protocolo")
        return (f"cita valor(es) {values} que não aparecem nos resultados das ferramentas. Não calcule "
                "nem estime valores: use apenas os devolvidos pelas ferramentas (para totais e parcelas, "
                "chame payment_options) ou consulte a ferramenta adequada")


def verify_reply(text: str, messages: list[AnyMessage]) -> list[ReplyIssue]:
    issues = []
    if tickets := ungrounded_protocols(text, messages):
        issues.append(ReplyIssue("ticket", tuple(sorted(tickets))))
    if prices := ungrounded_prices(text, messages):
        issues.append(ReplyIssue("price", tuple(f"R$ {p:.2f}".replace(".", ",") for p in sorted(prices))))
    return issues


def correction_message(issues: list[ReplyIssue]) -> HumanMessage:
    details = "; ".join(f"Sua resposta {issue.describe()}" for issue in issues)
    return HumanMessage(
        f"[Verificação automática interna, não é mensagem do cliente] {details}. Reescreva a "
        "resposta ao cliente corrigindo apenas esse ponto e mantendo todo o resto, inclusive "
        "avisos importantes. O cliente não vê esta verificação: não a mencione, não peça "
        "desculpas por ela e não diga que 'calculou' algo."
    )
