"""Verificação determinística das respostas antes de chegarem ao cliente.

Motivação (encontrada em teste real): o modelo disse "vou registrar seu caso", não chamou
a ferramenta e inventou um protocolo ("#ESCALATE-7-DEFEITO-LETICIA"). Instruções no prompt
reduzem, mas não eliminam esse tipo de alucinação; por isso conferimos a resposta contra os
resultados das ferramentas presentes no histórico.

Regra atual: todo código de protocolo citado na resposta precisa ter sido devolvido por
`escalate_to_human` nesta conversa.
"""

from __future__ import annotations

import re

from langchain_core.messages import AnyMessage, ToolMessage

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
