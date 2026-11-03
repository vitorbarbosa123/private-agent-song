"""Tratamento da tabela de categorias."""

from __future__ import annotations

import pandas as pd

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import clean_text, drop_duplicate_ids, drop_null, normalize_for_search, parse_int

TABLE = "categories"


def clean_categories(raw: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    df = raw.copy()
    df["category_id"] = [
        parse_int(v, log=log, table=TABLE, record_id=v, field="category_id") for v in df["category_id"]
    ]
    df = drop_null(df, "category_id", log=log, table=TABLE, id_col="category_id")
    df["category_id"] = df["category_id"].astype(int)
    df = drop_duplicate_ids(df, "category_id", log=log, table=TABLE)
    df["name"] = df["name"].map(clean_text)
    df["description"] = df["description"].map(clean_text)
    df["name_search"] = df["name"].map(normalize_for_search)
    return df.sort_values("category_id").reset_index(drop=True)


def flag_empty_categories(categories: pd.DataFrame, products: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    """Adiciona contagem de produtos e sinaliza categorias sem nenhum item vendável."""
    counts = products.groupby("category_id").size()
    sellable = products[products["is_sellable"]].groupby("category_id").size()
    out = categories.copy()
    out["product_count"] = out["category_id"].map(counts).fillna(0).astype(int)
    out["sellable_count"] = out["category_id"].map(sellable).fillna(0).astype(int)
    for row in out.itertuples():
        if row.product_count == 0:
            log.add(TABLE, row.category_id, "empty_category", Severity.WARNING,
                    f"Categoria '{row.name}' não possui nenhum produto cadastrado, embora o manual "
                    "cite essa linha de instrumentos.",
                    "Mantida. O agente deve informar que não há itens disponíveis no momento.")
        elif row.sellable_count == 0:
            log.add(TABLE, row.category_id, "no_sellable_products", Severity.INFO,
                    f"Categoria '{row.name}' não possui produtos disponíveis para venda.", "Mantida.")
    return out
