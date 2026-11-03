"""Funções auxiliares de parsing e normalização de texto."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

from emporio.data.issues import IssueLog, Severity

_WS = re.compile(r"\s+")
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")


def clean_text(value: object) -> str | None:
    """Remove caracteres invisíveis e espaços redundantes; vazio vira `None`."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = _WS.sub(" ", _INVISIBLE.sub("", str(value))).strip()
    return text or None


def normalize_for_search(value: object) -> str:
    """Minúsculas e sem acentos, para buscas tolerantes ('violao' encontra 'Violão')."""
    text = clean_text(value) or ""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def parse_int(
    value: object, *, log: IssueLog, table: str, record_id: object, field: str
) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is None or not number.is_integer():
        log.add(table, record_id, f"invalid_{field}", Severity.ERROR,
                f"Valor não inteiro em '{field}': {text!r}.", "Valor anulado.")
        return None
    return int(number)


def parse_float(
    value: object, *, log: IssueLog, table: str, record_id: object, field: str
) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        log.add(table, record_id, f"invalid_{field}", Severity.ERROR,
                f"Valor não numérico em '{field}': {text!r}.", "Valor anulado.")
        return None


def parse_date(
    value: object, *, log: IssueLog, table: str, record_id: object, field: str
) -> date | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        log.add(table, record_id, f"invalid_{field}", Severity.ERROR,
                f"Data inválida em '{field}': {text!r} (esperado AAAA-MM-DD).", "Valor anulado.")
        return None


def parse_bool(
    value: object, *, log: IssueLog, table: str, record_id: object, field: str
) -> bool | None:
    text = normalize_for_search(value)
    if text in {"1", "true", "sim", "yes"}:
        return True
    if text in {"0", "false", "nao", "no"}:
        return False
    log.add(table, record_id, f"invalid_{field}", Severity.ERROR,
            f"Booleano inválido em '{field}': {value!r}.", "Valor anulado.")
    return None


def drop_duplicate_ids(df: pd.DataFrame, id_col: str, *, log: IssueLog, table: str) -> pd.DataFrame:
    """Mantém a primeira ocorrência de cada id e registra as duplicatas."""
    duplicated = df[id_col].duplicated(keep="first")
    for rid in df.loc[duplicated, id_col]:
        log.add(table, rid, "duplicate_id", Severity.ERROR,
                f"'{id_col}' {rid} aparece mais de uma vez.", "Mantida a primeira ocorrência.")
    return df.loc[~duplicated].copy()


def drop_null(df: pd.DataFrame, col: str, *, log: IssueLog, table: str, id_col: str) -> pd.DataFrame:
    missing = df[col].isna()
    for rid in df.loc[missing, id_col]:
        log.add(table, rid, f"missing_{col}", Severity.ERROR,
                f"Campo obrigatório '{col}' ausente ou inválido.", "Registro descartado.")
    return df.loc[~missing].copy()


def format_brl(value: float) -> str:
    """1234.5 -> 'R$ 1.234,50'."""
    return "R$ " + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
