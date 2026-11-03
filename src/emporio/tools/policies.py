"""Ferramenta de consulta ao manual de políticas (RAG).

Além dos trechos recuperados, devolve as **interpretações oficiais** (`policy_rules.RESOLUTIONS`)
que se aplicam à seção mais relevante. Exemplo: se a busca retorna a seção 7, que cita o
WhatsApp (67) 3321-4500, a resposta também traz a decisão de usar o número canônico
(67) 3341-4444. Assim o modelo não repete uma contradição do manual.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from emporio.policy_rules import RESOLUTIONS, PolicyResolution
from emporio.tools.context import ToolContext

_SECTION_REF = re.compile(r"\d+(?:\.\d+)?|Capa")


class SearchPoliciesInput(BaseModel):
    query: str = Field(min_length=2, description="Pergunta do cliente sobre regras da loja, em linguagem natural.")
    k: int = Field(default=3, ge=1, le=5, description="Quantidade de trechos.")


class PolicyExcerpt(BaseModel):
    section: str
    title: str
    text: str


class SearchPoliciesResult(BaseModel):
    excerpts: list[PolicyExcerpt]
    official_interpretations: list[str] = Field(
        default_factory=list,
        description="Decisões sobre trechos ambíguos ou contraditórios. Prevalecem sobre o texto do manual.",
    )
    notes: list[str] = Field(default_factory=list)


def resolution_sections(resolution: PolicyResolution) -> set[str]:
    return {"0" if ref == "Capa" else ref for ref in _SECTION_REF.findall(resolution.sections)}


def search_policies(ctx: ToolContext, args: SearchPoliciesInput) -> SearchPoliciesResult:
    if ctx.policies is None:
        raise RuntimeError("Busca no manual indisponível neste contexto.")
    hits = ctx.policies.search(args.query, k=args.k)
    # Só a seção mais relevante: trechos secundários costumam ser tangenciais e trariam
    # interpretações fora de contexto (ex.: parcelamento numa pergunta sobre LGPD).
    top = hits[0].chunk.section_id if hits else None
    interpretations = [f"{r.topic}: {r.decision}" for r in RESOLUTIONS if top in resolution_sections(r)]
    notes = [
        "Responda somente com base nestes trechos e cite a seção quando ajudar o cliente. "
        "Se a resposta não estiver aqui, diga que vai confirmar com a equipe (manual, seção 10).",
    ]
    if ctx.policies.degraded:
        notes.append("Busca semântica indisponível agora; resultados da busca por palavras-chave.")
    return SearchPoliciesResult(
        excerpts=[PolicyExcerpt(section=h.chunk.section_id, title=h.chunk.heading, text=h.chunk.text) for h in hits],
        official_interpretations=interpretations,
        notes=notes,
    )
