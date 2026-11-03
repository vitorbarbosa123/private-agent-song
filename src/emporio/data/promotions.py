"""Tratamento das promoções e cálculo do preço vigente de cada produto.

Regras aplicadas (manual, seção 6.2):
- só vale promoção com `is_active = 1` (a tabela não tem datas de vigência);
- promoções não são cumulativas: se houver mais de uma ativa para o mesmo
  produto, vale apenas a de maior desconto;
- o desconto de 5% no PIX não se aplica sobre preço promocional;
- o preço promocional deve ser exibido junto do original e do percentual.
"""

from __future__ import annotations

import pandas as pd

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import clean_text, drop_duplicate_ids, drop_null, parse_bool, parse_float, parse_int
from emporio.policy_rules import PIX_DISCOUNT_PERCENT, round_brl

TABLE = "promotions"


def clean_promotions(raw: pd.DataFrame, products: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    df = raw.copy()
    df["promotion_id"] = [
        parse_int(v, log=log, table=TABLE, record_id=v, field="promotion_id") for v in df["promotion_id"]
    ]
    df = drop_null(df, "promotion_id", log=log, table=TABLE, id_col="promotion_id")
    df["promotion_id"] = df["promotion_id"].astype(int)
    df = drop_duplicate_ids(df, "promotion_id", log=log, table=TABLE)

    known_products = set(products["product_id"])
    records: list[dict[str, object]] = []
    for row in df.to_dict("records"):
        pid = row["promotion_id"]
        kw = {"log": log, "table": TABLE, "record_id": pid}
        product_id = parse_int(row["product_id"], field="product_id", **kw)
        discount = parse_float(row["discount_percent"], field="discount_percent", **kw)
        is_active = parse_bool(row["is_active"], field="is_active", **kw)

        if product_id not in known_products:
            log.add(TABLE, pid, "unknown_product", Severity.ERROR,
                    f"Promoção aponta para product_id inexistente ({row['product_id']!r}).",
                    "Promoção descartada.")
            continue
        if discount is None or not 0 < discount < 100:
            log.add(TABLE, pid, "invalid_discount", Severity.ERROR,
                    f"Percentual de desconto inválido: {row['discount_percent']!r}.",
                    "Promoção descartada.")
            continue
        if is_active is None:
            is_active = False  # na dúvida, não prometer desconto (seção 7.3)

        records.append({
            "promotion_id": pid,
            "product_id": product_id,
            "discount_percent": discount,
            "name": clean_text(row["description"]),
            "is_active": is_active,
        })

    promotions = pd.DataFrame.from_records(records)
    _flag_multiple_promotions(promotions, log)
    return promotions.sort_values("promotion_id").reset_index(drop=True)


def _flag_multiple_promotions(promotions: pd.DataFrame, log: IssueLog) -> None:
    for product_id, group in promotions.groupby("product_id"):
        if len(group) < 2:
            continue
        active = group[group["is_active"]]
        ids = ", ".join(str(i) for i in group["promotion_id"])
        if len(active) > 1:
            log.add(TABLE, ids, "multiple_active_promotions", Severity.WARNING,
                    f"Produto {product_id} tem {len(active)} promoções ativas simultâneas.",
                    "Promoções não são cumulativas (6.2): vale somente a de maior desconto.")
        else:
            log.add(TABLE, ids, "multiple_promotions_history", Severity.INFO,
                    f"Produto {product_id} possui {len(group)} promoções cadastradas "
                    f"({len(active)} ativa).",
                    "Apenas promoções ativas são consideradas no preço vigente.")


def apply_pricing(products: pd.DataFrame, promotions: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    """Adiciona ao catálogo o preço vigente (promoção ativa ou PIX)."""
    active = promotions[promotions["is_active"]].sort_values(
        ["product_id", "discount_percent"], ascending=[True, False]
    )
    best = active.drop_duplicates("product_id").set_index("product_id")

    out = products.copy()
    out["promotion_id"] = out["product_id"].map(best["promotion_id"]).astype("Int64")
    out["promotion_name"] = out["product_id"].map(best["name"])
    out["promotion_discount_percent"] = out["product_id"].map(best["discount_percent"])

    def promo_price(row: pd.Series) -> float | None:
        if pd.isna(row["promotion_discount_percent"]) or pd.isna(row["price_brl"]):
            return None
        factor = 1 - row["promotion_discount_percent"] / 100
        return float(round_brl(row["price_brl"] * factor))

    def pix_price(row: pd.Series) -> float | None:
        if pd.isna(row["price_brl"]) or pd.notna(row["promotion_discount_percent"]):
            return None  # PIX não acumula com promoção
        return float(round_brl(row["price_brl"] * (1 - float(PIX_DISCOUNT_PERCENT) / 100)))

    out["promotion_price_brl"] = out.apply(promo_price, axis=1)
    out["pix_price_brl"] = out.apply(pix_price, axis=1)

    for row in out[out["promotion_id"].notna() & ~out["is_sellable"]].itertuples():
        log.add(TABLE, row.promotion_id, "promotion_on_unavailable_product", Severity.WARNING,
                f"Promoção ativa para '{row.name}', que não está disponível ({row.availability}).",
                "Mantida; o agente deve informar a indisponibilidade antes do desconto.")
    return out
