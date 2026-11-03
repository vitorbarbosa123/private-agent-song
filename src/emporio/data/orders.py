"""Tratamento de pedidos e itens de pedido.

Pedidos são registros históricos: **nunca alteramos valores cobrados**. Divergências
(total vs. soma dos itens, parcelamento fora da política, status incoerente com o
rastreio) são sinalizadas em colunas derivadas e no relatório.
"""

from __future__ import annotations

import re

import pandas as pd

from emporio.data.issues import IssueLog, Severity
from emporio.data.utils import (
    clean_text,
    drop_duplicate_ids,
    drop_null,
    format_brl,
    normalize_for_search,
    parse_date,
    parse_float,
    parse_int,
)
from emporio.policy_rules import (
    PAYMENT_TYPES,
    is_installment_plan_allowed,
    min_installment_value,
    round_brl,
)

ORDERS = "orders"
ITEMS = "order_items"

VALID_STATUSES = ("pending", "confirmed", "shipped", "delivered", "cancelled")
STATUSES_WITH_TRACKING = {"shipped", "delivered"}
# Formato descrito no manual (5.3): BR + 9 caracteres alfanuméricos + BR.
TRACKING_CODE = re.compile(r"^BR[A-Z0-9]{9}BR$")
_PAYMENT = re.compile(r"^(?P<type>[a-z]+)(?:_(?P<n>\d+)x)?$")
TOTAL_TOLERANCE_BRL = 0.01


def parse_payment_method(value: object) -> tuple[str | None, int | None]:
    """'credit_6x' -> ('credit', 6); 'pix' -> ('pix', 1); inválido -> (None, None)."""
    match = _PAYMENT.match(normalize_for_search(value))
    if not match or match["type"] not in PAYMENT_TYPES:
        return None, None
    installments = int(match["n"]) if match["n"] else 1
    if match["type"] != "credit" and installments != 1:
        return None, None
    return match["type"], installments


def clean_order_items(
    raw: pd.DataFrame, products: pd.DataFrame, log: IssueLog
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    known_products = set(products["product_id"])
    for idx, row in enumerate(raw.to_dict("records"), start=2):  # linha 1 = cabeçalho
        rid = f"linha {idx}"
        kw = {"log": log, "table": ITEMS, "record_id": rid}
        order_id = parse_int(row["order_id"], field="order_id", **kw)
        product_id = parse_int(row["product_id"], field="product_id", **kw)
        quantity = parse_int(row["quantity"], field="quantity", **kw)
        if order_id is None:
            log.add(ITEMS, rid, "missing_order_id", Severity.ERROR, "Item sem pedido.", "Descartado.")
            continue
        if product_id not in known_products:
            log.add(ITEMS, rid, "unknown_product", Severity.ERROR,
                    f"Item do pedido {order_id} aponta para produto inexistente "
                    f"({row['product_id']!r}).", "Descartado.")
            continue
        if quantity is None or quantity <= 0:
            log.add(ITEMS, rid, "invalid_quantity", Severity.ERROR,
                    f"Quantidade inválida no pedido {order_id}: {row['quantity']!r}.", "Descartado.")
            continue
        records.append({"order_id": order_id, "product_id": product_id, "quantity": quantity})

    items = pd.DataFrame.from_records(records, columns=["order_id", "product_id", "quantity"])
    dupes = items.duplicated(["order_id", "product_id"], keep=False)
    for (order_id, product_id), _ in items[dupes].groupby(["order_id", "product_id"]):
        log.add(ITEMS, f"{order_id}/{product_id}", "duplicate_item", Severity.WARNING,
                f"Produto {product_id} aparece em mais de uma linha do pedido {order_id}.",
                "Linhas consolidadas somando as quantidades.")
    items = items.groupby(["order_id", "product_id"], as_index=False)["quantity"].sum()

    prices = products.set_index("product_id")["price_brl"]
    items["product_name"] = items["product_id"].map(products.set_index("product_id")["name"])
    items["unit_price_catalog_brl"] = items["product_id"].map(prices)
    items["line_total_catalog_brl"] = (items["unit_price_catalog_brl"] * items["quantity"]).round(2)
    return items


def clean_orders(
    raw: pd.DataFrame,
    items: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
    log: IssueLog,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (pedidos, itens), já com itens órfãos removidos."""
    df = raw.copy()
    df["order_id"] = [parse_int(v, log=log, table=ORDERS, record_id=v, field="order_id") for v in df["order_id"]]
    df = drop_null(df, "order_id", log=log, table=ORDERS, id_col="order_id")
    df["order_id"] = df["order_id"].astype(int)
    df = drop_duplicate_ids(df, "order_id", log=log, table=ORDERS)

    known_customers = set(customers["customer_id"])
    records: list[dict[str, object]] = []
    for row in df.to_dict("records"):
        oid = row["order_id"]
        kw = {"log": log, "table": ORDERS, "record_id": oid}

        customer_id = parse_int(row["customer_id"], field="customer_id", **kw)
        if customer_id not in known_customers:
            log.add(ORDERS, oid, "unknown_customer", Severity.ERROR,
                    f"customer_id {row['customer_id']!r} não existe.",
                    "Pedido mantido, mas não poderá ser autenticado por cliente.")

        status = normalize_for_search(row["status"]) or None
        if status not in VALID_STATUSES:
            log.add(ORDERS, oid, "invalid_status", Severity.ERROR,
                    f"Status desconhecido: {row['status']!r}.", "Status anulado.")
            status = None

        order_date = parse_date(row["order_date"], field="order_date", **kw)
        estimated = parse_date(row["estimated_delivery"], field="estimated_delivery", **kw)
        total = parse_float(row["total_brl"], field="total_brl", **kw)
        if total is not None and total <= 0:
            log.add(ORDERS, oid, "invalid_total", Severity.ERROR,
                    f"Total não positivo: {total}.", "Total anulado.")
            total = None

        payment_type, installments = parse_payment_method(row["payment_method"])
        if payment_type is None:
            log.add(ORDERS, oid, "invalid_payment_method", Severity.ERROR,
                    f"Forma de pagamento não reconhecida: {row['payment_method']!r}.",
                    "Forma de pagamento anulada.")

        installment_value = None
        plan_valid: bool | None = None
        if payment_type == "credit" and total is not None and installments:
            installment_value = float(round_brl(total / installments))
            plan_valid = is_installment_plan_allowed(total, installments)
            if not plan_valid:
                minimum = min_installment_value(installments)
                rule = f"mínimo de {format_brl(float(minimum))}" if minimum is not None else "máximo de 12x"
                log.add(ORDERS, oid, "installment_policy_violation", Severity.WARNING,
                        f"Parcelamento em {installments}x de {format_brl(installment_value)} viola a "
                        f"política vigente (seção 3.1: {rule} por parcela).",
                        "Mantido (registro histórico); installment_plan_valid=False. O agente não "
                        "deve usar esse pedido como referência de condição de pagamento.")

        tracking = (clean_text(row["tracking_code"]) or "").upper() or None
        if tracking and not TRACKING_CODE.match(tracking):
            log.add(ORDERS, oid, "invalid_tracking_code", Severity.WARNING,
                    f"Código de rastreio fora do formato BR+9+BR: {tracking!r}.",
                    "Mantido; sinalizado.")
        if status in STATUSES_WITH_TRACKING and not tracking:
            log.add(ORDERS, oid, "missing_tracking_code", Severity.WARNING,
                    f"Pedido '{status}' sem código de rastreio.",
                    "O agente deve encaminhar o cliente a um atendente.")
        if status not in STATUSES_WITH_TRACKING and tracking:
            log.add(ORDERS, oid, "unexpected_tracking_code", Severity.WARNING,
                    f"Pedido '{status}' já possui código de rastreio.", "Mantido; sinalizado.")
        if status in STATUSES_WITH_TRACKING and estimated is None:
            log.add(ORDERS, oid, "missing_estimated_delivery", Severity.WARNING,
                    f"Pedido '{status}' sem previsão de entrega.", "Sinalizado.")
        if order_date and estimated and estimated < order_date:
            log.add(ORDERS, oid, "delivery_before_order", Severity.ERROR,
                    f"Previsão de entrega ({estimated}) anterior à data do pedido ({order_date}).",
                    "Previsão de entrega anulada.")
            estimated = None

        notes = clean_text(row["notes"])
        if status == "cancelled" and not notes:
            log.add(ORDERS, oid, "cancelled_without_reason", Severity.INFO,
                    "Pedido cancelado sem motivo registrado.", "Sinalizado.")

        records.append({
            "order_id": oid,
            "customer_id": customer_id,
            "order_date": order_date,
            "status": status,
            "total_brl": total,
            "payment_method": clean_text(row["payment_method"]),
            "payment_type": payment_type,
            "installments": installments,
            "installment_value_brl": installment_value,
            "installment_plan_valid": plan_valid,
            "tracking_code": tracking,
            "estimated_delivery": estimated,
            "notes": notes,
        })

    orders = pd.DataFrame.from_records(records)
    known_orders = set(orders["order_id"])
    orphans = items[~items["order_id"].isin(known_orders)]
    for row in orphans.itertuples():
        log.add(ITEMS, f"{row.order_id}/{row.product_id}", "orphan_item", Severity.ERROR,
                f"Item aponta para pedido inexistente ({row.order_id}).", "Descartado.")
    items = items[items["order_id"].isin(known_orders)].reset_index(drop=True)

    orders = _reconcile_totals(orders, items, log)
    _check_items_against_products(orders, items, products, log)
    return orders.sort_values("order_id").reset_index(drop=True), items


def _reconcile_totals(orders: pd.DataFrame, items: pd.DataFrame, log: IssueLog) -> pd.DataFrame:
    summary = items.groupby("order_id").agg(
        items_count=("quantity", "sum"), items_total_catalog_brl=("line_total_catalog_brl", "sum")
    )
    out = orders.merge(summary, how="left", left_on="order_id", right_index=True)
    out["items_count"] = out["items_count"].fillna(0).astype(int)
    out["items_total_catalog_brl"] = out["items_total_catalog_brl"].round(2)
    out["total_divergence_brl"] = (out["total_brl"] - out["items_total_catalog_brl"]).round(2)

    for row in out.itertuples():
        if row.items_count == 0:
            log.add(ORDERS, row.order_id, "order_without_items", Severity.ERROR,
                    "Pedido sem nenhum item.", "Mantido; o agente não consegue detalhar os itens.")
        elif pd.notna(row.total_divergence_brl) and abs(row.total_divergence_brl) > TOTAL_TOLERANCE_BRL:
            log.add(ORDERS, row.order_id, "total_mismatch", Severity.WARNING,
                    f"Total registrado {format_brl(row.total_brl)} difere da soma dos itens a preço de "
                    f"catálogo atual {format_brl(row.items_total_catalog_brl)} "
                    f"(diferença de {format_brl(abs(row.total_divergence_brl))} "
                    f"{'a menos' if row.total_divergence_brl < 0 else 'a mais'}).",
                    "Mantido o total registrado (valor efetivamente cobrado). Diferença exposta em "
                    "'total_divergence_brl'; o agente informa o total registrado.")
    return out


def _check_items_against_products(
    orders: pd.DataFrame, items: pd.DataFrame, products: pd.DataFrame, log: IssueLog
) -> None:
    merged = items.merge(orders[["order_id", "order_date", "status"]], on="order_id").merge(
        products[["product_id", "name", "status", "created_at"]],
        on="product_id", suffixes=("_order", "_product"),
    )
    for row in merged.itertuples():
        rid = f"{row.order_id}/{row.product_id}"
        if row.status_product == "coming_soon" and row.status_order != "cancelled":
            log.add(ITEMS, rid, "coming_soon_product_sold", Severity.WARNING,
                    f"Pedido {row.order_id} ({row.status_order}) contém '{row.name}', que está "
                    "cadastrado como 'coming_soon' (ainda não lançado).",
                    "Mantido; indica status de produto desatualizado no cadastro.")
        if pd.notna(row.created_at) and pd.notna(row.order_date) and row.order_date < row.created_at:
            log.add(ITEMS, rid, "order_before_product_created", Severity.WARNING,
                    f"Pedido {row.order_id} ({row.order_date}) é anterior ao cadastro do produto "
                    f"'{row.name}' ({row.created_at}).", "Mantido; sinalizado.")
