"""Extração e saneamento do manual de políticas (PDF).

- Extrai o texto preservando o layout (o modo padrão do pypdf quebra cada palavra
  em uma linha neste PDF, gerado pelo Google Docs);
- remove cabeçalhos/rodapés repetidos e caracteres invisíveis;
- divide o texto em seções numeradas (1, 1.1, 1.2, 2, ...), prontas para RAG;
- detecta divergências de contato (telefones/e-mails diferentes no documento).
  As decisões sobre cada conflito ficam em `emporio.policy_rules.RESOLUTIONS`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import clean_text
from emporio.policy_rules import STORE_INFO

TABLE = "policies"

_HEADER = re.compile(r"^Empório da Música\s+Manual de Políticas e Procedimentos$")
_FOOTER = re.compile(r"^Página \d+$")
_TOP_SECTION = re.compile(r"^(\d+)\.\s+(\S.*)$")
_SUB_SECTION = re.compile(r"^(\d+)\.(\d+)\s+(\S.*)$")
_TABLE_GAP = re.compile(r"\s{3,}")
_LIST_MARKER = re.compile(r"^([•▸‣]|\d+\.)\s{2,}")
_PHONE = re.compile(r"\(\d{2}\)\s*\d{4,5}\s*-\s*\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


@dataclass
class PolicySection:
    section_id: str  # "0" = capa, "4", "4.1", ...
    title: str
    parent_id: str | None
    text: str


def extract_pdf_text(pdf_path: Path) -> list[str]:
    """Linhas de texto do PDF, sem cabeçalho, rodapé e caracteres invisíveis."""
    reader = PdfReader(pdf_path)
    lines: list[str] = []
    for page in reader.pages:
        for raw_line in page.extract_text(extraction_mode="layout").splitlines():
            stripped = raw_line.strip()
            # Marcadores de lista vêm seguidos de vários espaços; normaliza antes de
            # detectar colunas de tabela, senão '•    texto' viraria '• | texto'.
            stripped = _LIST_MARKER.sub(
                lambda m: f"{m[1]} " if m[1][0].isdigit() else "- ", stripped
            )
            # Linhas de tabela: colunas separadas por 3+ espaços viram " | ".
            line = clean_text(_TABLE_GAP.sub(" | ", stripped)) if stripped else None
            if line is None or _HEADER.match(line) or _FOOTER.match(line):
                continue
            lines.append(line)
    return lines


def split_sections(lines: list[str]) -> list[PolicySection]:
    """Divide em seções. Seções de topo precisam ser sequenciais (1, 2, 3...), o que
    evita confundir listas numeradas (ex.: '1. Saudação' na seção 7.2) com títulos."""
    sections = [PolicySection("0", "Capa", None, "")]
    body: list[list[str]] = [[]]
    current_top = 0

    for line in lines:
        sub = _SUB_SECTION.match(line)
        top = _TOP_SECTION.match(line)
        if sub and int(sub[1]) == current_top:
            sections.append(PolicySection(f"{sub[1]}.{sub[2]}", sub[3], str(current_top), ""))
            body.append([])
        elif top and int(top[1]) == current_top + 1:
            current_top += 1
            sections.append(PolicySection(str(current_top), top[2], None, ""))
            body.append([])
        else:
            body[-1].append(line)

    for section, content in zip(sections, body, strict=True):
        section.text = _join_wrapped_lines(content)
    return sections


def _join_wrapped_lines(lines: list[str]) -> str:
    """Junta linhas quebradas pelo layout do PDF, mantendo itens de lista e tabelas."""
    out: list[str] = []
    for line in lines:
        starts_block = line.startswith("- ") or re.match(r"^\d+\.\s", line) or " | " in line
        if out and not starts_block and " | " not in out[-1] and not out[-1].endswith((".", ":")):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return "\n".join(out)


def detect_contact_conflicts(lines: list[str], log: IssueLog) -> None:
    text = "\n".join(lines)
    phones = sorted({re.sub(r"\s", "", p) for p in _PHONE.findall(text)})
    if len(phones) > 1:
        log.add(TABLE, None, "conflicting_phones", Severity.WARNING,
                f"O manual cita telefones diferentes para a loja: {', '.join(phones)}.",
                f"Adotado {STORE_INFO['phone_whatsapp']} como canônico (ver resolução "
                "'Telefone / WhatsApp').")
    emails = sorted(set(_EMAIL.findall(text)))
    if len(emails) > 1:
        log.add(TABLE, None, "conflicting_emails", Severity.WARNING,
                f"O manual cita grafias diferentes de e-mail: {', '.join(emails)}.",
                f"Adotado {STORE_INFO['email']} como canônico (ver resolução 'E-mail').")


def render_markdown(sections: list[PolicySection]) -> str:
    parts = [
        "# Manual de Políticas e Procedimentos — Empório da Música",
        "",
        "> Texto extraído automaticamente de `data/políticas_da_loja.pdf` (v2.1, jun/2025).",
        "> Conflitos internos do manual e a interpretação adotada estão em `store_facts.json`.",
        "",
    ]
    for s in sections:
        level = "###" if s.parent_id else "##"
        parts += [f"{level} {s.section_id}. {s.title}" if s.section_id != "0" else "## Capa", ""]
        if s.text:
            parts += [s.text, ""]
    return "\n".join(parts)


def process_policies(pdf_path: Path, log: IssueLog) -> tuple[list[dict[str, str | None]], str]:
    lines = extract_pdf_text(pdf_path)
    sections = split_sections(lines)
    if len(sections) < 2:
        log.add(TABLE, None, "no_sections_found", Severity.ERROR,
                "Nenhuma seção numerada foi encontrada no PDF.", "Texto mantido como bloco único.")
    detect_contact_conflicts(lines, log)
    return [asdict(s) for s in sections], render_markdown(sections)
