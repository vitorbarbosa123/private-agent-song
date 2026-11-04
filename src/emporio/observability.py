"""Observabilidade com Langfuse: rastreamento de cada mensagem do cliente.

Ativado só quando LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY estão configuradas; sem elas,
o agente funciona igual e nada é enviado. Para um Langfuse local, sem criar conta:

    docker compose --profile observability up     # Langfuse em http://localhost:3000

O que é registrado:
- **um trace por mensagem**, agrupado por conversa (sessão do Langfuse), com o grafo do
  LangGraph: cada chamada ao modelo (tokens, latência), cada ferramenta e seus resultados;
- **scores** por mensagem: resposta de fallback, número de ferramentas, correções feitas pela
  verificação de saída, alertas dos guardrails de entrada e custo informado pelo provedor.

Privacidade (LGPD): cartões, e-mails, telefones e CPFs são mascarados ANTES de sair do
processo (parâmetro `mask` do SDK). O guardrail de entrada já remove cartões do histórico,
mas o rastreamento captura a entrada do grafo antes dele, então a máscara precisa cobri-los.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from emporio.config import Settings
from emporio.privacy import mask_card_numbers

if TYPE_CHECKING:
    from emporio.agent.graph import AgentReply

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")


def mask_personal_data(data: Any) -> Any:
    """Mascara e-mails, telefones e CPFs em qualquer estrutura (str, dict, list)."""
    if isinstance(data, str):
        data = mask_card_numbers(data)
        data = _EMAIL.sub("[e-mail]", data)
        data = _CPF.sub("[cpf]", data)
        return _PHONE.sub("[telefone]", data)
    if isinstance(data, dict):
        return {k: mask_personal_data(v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return type(data)(mask_personal_data(v) for v in data)
    return data


def _mask(*, data: Any, **_: Any) -> Any:  # assinatura exigida pelo SDK
    return mask_personal_data(data)


class Tracer:
    """Fachada mínima sobre o Langfuse; vira no-op quando não configurado."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
        self._client = None
        self._public_key = settings.langfuse_public_key
        if not self.enabled:
            return
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),  # type: ignore[union-attr]
                host=settings.langfuse_host,
                environment=settings.langfuse_environment,
                mask=_mask,
            )
        except Exception as exc:  # noqa: BLE001 — observabilidade nunca derruba o atendimento
            logger.warning("Langfuse indisponível (%s); seguindo sem rastreamento.", exc)
            self.enabled = False

    @contextmanager
    def turn(self, *, session_id: str, model: str, metadata: dict[str, Any]) -> Iterator[list[Any]]:
        """Contexto de uma mensagem do cliente: devolve os callbacks para o LangGraph."""
        if not self.enabled:
            yield []
            return
        from langfuse import propagate_attributes
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler(public_key=self._public_key)
        with propagate_attributes(session_id=session_id, trace_name="mensagem-do-cliente",
                                  tags=["emporio-agent", model], metadata=metadata):
            yield [handler]
        self._last_trace_id = getattr(handler, "last_trace_id", None)

    def record(self, reply: AgentReply, *, guard_flags: list[str], verification_issues: list[str]) -> None:
        """Anexa ao trace da última mensagem os indicadores de qualidade do turno."""
        trace_id = getattr(self, "_last_trace_id", None)
        if not self.enabled or self._client is None or not trace_id:
            return
        scores: list[tuple[str, Any, str]] = [
            ("fallback", 1 if reply.error else 0, "BOOLEAN"),
            ("ferramentas_chamadas", len(reply.tool_calls), "NUMERIC"),
            ("correcoes_da_verificacao", len(verification_issues), "NUMERIC"),
        ]
        if reply.cost_usd is not None:
            scores.append(("custo_provedor_usd", reply.cost_usd, "NUMERIC"))
        for flag in guard_flags:
            scores.append(("guardrail_entrada", flag, "CATEGORICAL"))
        try:
            for name, value, kind in scores:
                comment = ", ".join(verification_issues) if name == "correcoes_da_verificacao" and value else None
                self._client.create_score(name=name, value=value, trace_id=trace_id, data_type=kind,
                                          comment=comment)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao registrar scores no Langfuse: %s", exc)

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()
