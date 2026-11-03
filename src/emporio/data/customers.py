"""Tratamento da base de clientes.

Dados pessoais (LGPD): o pipeline não remove nem mascara nada, mas gera colunas
normalizadas (`email_normalized`, `phone_digits`) para que o agente possa
autenticar o cliente comparando valores exatos, em vez de buscas aproximadas
que vazariam dados de terceiros.
"""

from __future__ import annotations

import re
from itertools import combinations

import pandas as pd

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import clean_text, drop_duplicate_ids, drop_null, normalize_for_search, parse_int

TABLE = "customers"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME_PARTICLES = {"da", "de", "do", "das", "dos", "e"}


def normalize_phone(value: object) -> str | None:
    digits = re.sub(r"\D", "", clean_text(value) or "")
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]  # remove código do país
    return digits or None


def _name_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in normalize_for_search(name).split() if t not in _NAME_PARTICLES)


def clean_customers(raw: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    df = raw.copy()
    df["customer_id"] = [
        parse_int(v, log=log, table=TABLE, record_id=v, field="customer_id") for v in df["customer_id"]
    ]
    df = drop_null(df, "customer_id", log=log, table=TABLE, id_col="customer_id")
    df["customer_id"] = df["customer_id"].astype(int)
    df = drop_duplicate_ids(df, "customer_id", log=log, table=TABLE)

    df["name"] = df["name"].map(clean_text)
    df["city"] = df["city"].map(clean_text)
    df["email"] = df["email"].map(clean_text)
    df["email_normalized"] = df["email"].map(lambda e: e.lower() if e else None)
    df["phone"] = df["phone"].map(clean_text)
    df["phone_digits"] = df["phone"].map(normalize_phone)
    df["name_search"] = df["name"].map(normalize_for_search)

    for row in df.itertuples():
        if not row.email_normalized or not _EMAIL.match(row.email_normalized):
            log.add(TABLE, row.customer_id, "invalid_email", Severity.WARNING,
                    f"E-mail ausente ou inválido: {row.email!r}.",
                    "Mantido; não pode ser usado para autenticação.")
        if not row.phone_digits or len(row.phone_digits) not in {10, 11}:
            log.add(TABLE, row.customer_id, "invalid_phone", Severity.WARNING,
                    f"Telefone ausente ou inválido: {row.phone!r}.",
                    "Mantido; não pode ser usado para autenticação.")

    df["email_shared"] = _flag_shared(df, "email_normalized", "shared_email", "e-mail", log)
    df["phone_shared"] = _flag_shared(df, "phone_digits", "shared_phone", "telefone", log)
    _flag_similar_names(df, log)
    return df.sort_values("customer_id").reset_index(drop=True)


def _flag_shared(df: pd.DataFrame, col: str, rule: str, label: str, log: IssueLog) -> pd.Series:
    shared = df[col].notna() & df[col].duplicated(keep=False)
    for value, group in df[shared].groupby(col):
        ids = ", ".join(str(i) for i in group["customer_id"])
        names = " / ".join(group["name"])
        log.add(TABLE, ids, rule, Severity.WARNING,
                f"Clientes distintos ({names}) compartilham o mesmo {label}: {value}.",
                f"Cadastros mantidos (não há base para fundi-los). O {label} sozinho não "
                "identifica o cliente: a autenticação exige número do pedido + e-mail/telefone.")
    return shared


def _flag_similar_names(df: pd.DataFrame, log: IssueLog) -> None:
    """Sinaliza pares cujo nome curto está contido no nome completo do outro."""
    tokens = {row.customer_id: _name_tokens(row.name or "") for row in df.itertuples()}
    names = dict(zip(df["customer_id"], df["name"], strict=True))
    for a, b in combinations(sorted(tokens), 2):
        ta, tb = tokens[a], tokens[b]
        shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if len(shorter) >= 2 and shorter < longer:
            log.add(TABLE, f"{a}, {b}", "possible_duplicate_customer", Severity.INFO,
                    f"Nomes possivelmente da mesma pessoa: '{names[a]}' e '{names[b]}'.",
                    "Nenhuma fusão automática; apenas sinalizado para revisão humana.")
