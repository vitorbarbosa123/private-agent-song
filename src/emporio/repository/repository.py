"""Acesso somente leitura aos dados tratados (SQLite gerado pelo pipeline).

Decisões:
- **Consultas fixas e parametrizadas.** O LLM nunca escreve SQL: ele escolhe uma
  ferramenta e os filtros, e este módulo monta a consulta a partir de trechos fixos com
  parâmetros vinculados (`?`). Isso elimina SQL injection e consultas alucinadas.
- **Conexão somente leitura** (`mode=ro`): o agente não altera dados.
- **Busca textual tolerante** (rapidfuzz + normalização sem acentos), porque clientes
  escrevem "takamine gd 20", "violao" ou "ukulele tenor".
- **Pedidos exigem autenticação** (número do pedido + e-mail ou telefone). A resposta é a
  mesma para "pedido inexistente" e "dados não conferem", para não revelar quais pedidos
  existem (LGPD).
"""

from __future__ import annotations

import hmac
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz

from emporio.data.customers import normalize_phone
from emporio.data.utils import normalize_for_search
from emporio.repository.models import (
    AVAILABILITY_LABELS,
    ORDER_STATUS_LABELS,
    Category,
    Order,
    OrderItem,
    Price,
    Product,
    ProductMatch,
    Promotion,
)

SortOrder = Literal["relevance", "price_asc", "price_desc"]

TEXT_MATCH_MIN_SCORE = 75.0
NAME_LOOKUP_MIN_SCORE = 70.0
CATEGORY_MIN_SCORE = 75.0

_PRODUCT_SELECT = """
    SELECT p.*, c.name AS category_name,
           COALESCE(p.promotion_price_brl, p.price_brl) AS current_price_brl
    FROM products p
    JOIN categories c ON c.category_id = p.category_id
"""


class DatabaseNotFoundError(FileNotFoundError):
    pass


_PLURAL_SUFFIX = re.compile(r"(oes|aes|aos|ao|es|s)$")
_TYPO_MIN_RATIO = 85


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _stem(token: str) -> str:
    """Stemming mínimo para plurais em português: violão/violões -> viol."""
    return _PLURAL_SUFFIX.sub("", token) if len(token) > 4 else token


def _token_matches(token: str, doc_tokens: list[str], compact_doc: str) -> bool:
    if _compact(token) and _compact(token) in compact_doc:  # "d28" acha "D-28"
        return True
    stem = _stem(token)
    for doc_token in doc_tokens:
        doc_stem = _stem(doc_token)
        # Prefixo: 'guitarr' casa 'guitarras'. No sentido inverso só aceita 1 letra de
        # diferença, senão 'violino' (violin) casaria 'violões' (viol).
        if len(stem) >= 3 and len(doc_stem) >= 3 and (
            doc_stem.startswith(stem) or (stem.startswith(doc_stem) and len(stem) - len(doc_stem) <= 1)
        ):
            return True
        if fuzz.ratio(token, doc_token) >= _TYPO_MIN_RATIO:  # erro de digitação: "yamha"
            return True
    return False


def text_score(query: str, document: str) -> float:
    """Similaridade 0-100 baseada na cobertura das palavras da busca.

    - Todas as palavras encontradas: 90-100, desempatado pela proximidade do texto inteiro.
    - Cobertura parcial: 50 + 40 x fração encontrada (2 de 3 palavras = ~77).
    Palavras "encontradas" toleram plural, hífens e pequenos erros de digitação.
    """
    q, doc = normalize_for_search(query), normalize_for_search(document)
    q_tokens, doc_tokens = q.split(), doc.split()
    if not q_tokens:
        return 0.0
    compact_doc = _compact(doc)
    matched = sum(_token_matches(t, doc_tokens, compact_doc) for t in q_tokens)
    if matched == len(q_tokens):
        return 90.0 + fuzz.token_sort_ratio(q, doc) / 10
    if matched == 0:
        return 0.0
    return 50.0 + 40.0 * matched / len(q_tokens)


class StoreRepository:
    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise DatabaseNotFoundError(
                f"Banco não encontrado em {db_path}. Rode `uv run emporio-clean-data`."
            )
        self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> StoreRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- Categorias ----------------------------------------------------------

    def list_categories(self) -> list[Category]:
        rows = self._conn.execute(
            "SELECT category_id, name, description, product_count, sellable_count "
            "FROM categories ORDER BY category_id"
        ).fetchall()
        return [Category(**dict(r)) for r in rows]

    def resolve_category(self, text: str) -> Category | None:
        """Encontra a categoria citada pelo cliente ('violão', 'bateria', 'violino')."""
        best: tuple[float, Category] | None = None
        for category in self.list_categories():
            # Coincidência no nome vale mais que na descrição: "baixo" deve achar
            # "Baixos", não "Cordas Orquestrais" (que cita "contrabaixos").
            score = max(
                text_score(text, category.name),
                0.9 * text_score(text, category.description or ""),
            )
            if best is None or score > best[0]:
                best = (score, category)
        if best and best[0] >= CATEGORY_MIN_SCORE:
            return best[1]
        return None

    # --- Produtos ------------------------------------------------------------

    def get_product(self, product_id: int) -> Product | None:
        row = self._conn.execute(f"{_PRODUCT_SELECT} WHERE p.product_id = ?", (product_id,)).fetchone()
        return _to_product(row) if row else None

    def search_products(
        self,
        *,
        text: str | None = None,
        category_id: int | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        brand: str | None = None,
        string_type: Literal["nylon", "aço"] | None = None,
        has_electronics: bool | None = None,
        only_available: bool = True,
        sort: SortOrder = "relevance",
        limit: int = 10,
    ) -> list[ProductMatch]:
        """Busca no catálogo. Filtros de preço usam o preço vigente (com promoção)."""
        clauses: list[str] = []
        params: list[object] = []
        if category_id is not None:
            clauses.append("p.category_id = ?")
            params.append(category_id)
        if min_price is not None:
            clauses.append("COALESCE(p.promotion_price_brl, p.price_brl) >= ?")
            params.append(min_price)
        if max_price is not None:
            clauses.append("COALESCE(p.promotion_price_brl, p.price_brl) <= ?")
            params.append(max_price)
        if brand:
            clauses.append("p.brand = ? COLLATE NOCASE")
            params.append(brand.strip())
        if string_type:
            clauses.append("json_extract(p.specs, '$.string_type') = ?")
            params.append(string_type)
        if has_electronics is not None:
            clauses.append("json_extract(p.specs, '$.electronics') = ?")
            params.append(1 if has_electronics else 0)
        if only_available:
            clauses.append("p.is_sellable = 1")

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(_PRODUCT_SELECT + where, params).fetchall()

        matches = []
        for row in rows:
            if text:
                score = text_score(text, f"{row['name']} {row['category_name']}")
                if score < TEXT_MATCH_MIN_SCORE:
                    continue
            else:
                score = 100.0
            matches.append(ProductMatch(product=_to_product(row), score=score))

        if sort == "price_desc":
            matches.sort(key=lambda m: -m.product.price.current_price_brl)
        elif sort == "price_asc" or not text:
            matches.sort(key=lambda m: m.product.price.current_price_brl)
        else:
            matches.sort(key=lambda m: (-m.score, m.product.price.current_price_brl))
        return matches[: max(1, limit)]

    def find_products_by_name(self, name: str, *, limit: int = 3) -> list[ProductMatch]:
        """Localiza um produto citado pelo nome, inclusive esgotados e fora de linha,
        para que o agente possa informar a situação em vez de dizer que não existe."""
        rows = self._conn.execute(_PRODUCT_SELECT).fetchall()
        scored = [(text_score(name, r["name"]), r) for r in rows]
        scored = [(s, r) for s, r in scored if s >= NAME_LOOKUP_MIN_SCORE]
        scored.sort(key=lambda sr: (-sr[0], -int(sr[1]["is_sellable"])))
        return [ProductMatch(product=_to_product(r), score=s) for s, r in scored[:limit]]

    def find_alternatives(self, product: Product, *, limit: int = 3) -> list[Product]:
        """Produtos disponíveis da mesma categoria (manual 7.3), priorizando o mesmo tipo de
        corda e de eletrônica (um violão de aço não substitui um clássico de nylon) e, depois,
        o preço mais próximo."""
        string_type = product.specs.get("string_type")
        electronics = product.specs.get("electronics")
        rows = self._conn.execute(
            f"""{_PRODUCT_SELECT}
            WHERE p.category_id = ? AND p.product_id != ? AND p.is_sellable = 1
            ORDER BY (json_extract(p.specs, '$.string_type') IS NOT ?),
                     (json_extract(p.specs, '$.electronics') IS NOT ?),
                     ABS(COALESCE(p.promotion_price_brl, p.price_brl) - ?)
            LIMIT ?""",
            (product.category_id, product.product_id, string_type,
             None if electronics is None else int(electronics), product.price.current_price_brl, limit),
        ).fetchall()
        return [_to_product(r) for r in rows]

    def list_active_promotions(self, *, only_available: bool = True) -> list[Promotion]:
        rows = self._conn.execute(
            f"""{_PRODUCT_SELECT}
            WHERE p.promotion_id IS NOT NULL {"AND p.is_sellable = 1" if only_available else ""}
            ORDER BY p.promotion_discount_percent DESC"""
        ).fetchall()
        return [
            Promotion(
                promotion_id=int(r["promotion_id"]),
                name=r["promotion_name"],
                discount_percent=r["promotion_discount_percent"],
                product=_to_product(r),
            )
            for r in rows
        ]

    # --- Pedidos -------------------------------------------------------------

    def get_order(self, order_id: int, *, email: str | None = None, phone: str | None = None) -> Order | None:
        """Retorna o pedido só se o e-mail e/ou telefone informados forem do cliente dono.

        Todos os dados informados precisam conferir. Retorna `None` tanto para pedido
        inexistente quanto para dados que não conferem.
        """
        email_norm = (email or "").strip().lower() or None
        phone_norm = normalize_phone(phone) if phone else None
        if not email_norm and not phone_norm:
            return None

        row = self._conn.execute(
            """SELECT o.*, c.name AS customer_name, c.email_normalized, c.phone_digits
               FROM orders o JOIN customers c ON c.customer_id = o.customer_id
               WHERE o.order_id = ?""",
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        if email_norm and not _same(email_norm, row["email_normalized"]):
            return None
        if phone_norm and not _same(phone_norm, row["phone_digits"]):
            return None

        items = self._conn.execute(
            "SELECT product_id, product_name, quantity FROM order_items WHERE order_id = ? ORDER BY product_id",
            (order_id,),
        ).fetchall()
        return Order(
            order_id=row["order_id"],
            customer_first_name=(row["customer_name"] or "").split(" ")[0],
            order_date=date.fromisoformat(row["order_date"]),
            status=row["status"],
            status_label=ORDER_STATUS_LABELS.get(row["status"], row["status"]),
            total_brl=row["total_brl"],
            payment_type=row["payment_type"],
            installments=row["installments"],
            installment_value_brl=row["installment_value_brl"],
            tracking_code=row["tracking_code"],
            estimated_delivery=date.fromisoformat(row["estimated_delivery"]) if row["estimated_delivery"] else None,
            notes=row["notes"],
            items=[OrderItem(**dict(i)) for i in items],
        )


def _same(given: str, stored: str | None) -> bool:
    """Comparação em tempo constante, para não vazar informação por tempo de resposta."""
    return stored is not None and hmac.compare_digest(given.encode(), stored.encode())


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _to_product(row: sqlite3.Row) -> Product:
    return Product(
        product_id=row["product_id"],
        name=row["name"],
        brand=row["brand"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        price=Price(
            list_price_brl=row["price_brl"],
            promotion_name=row["promotion_name"],
            promotion_discount_percent=_optional_float(row["promotion_discount_percent"]),
            promotion_price_brl=_optional_float(row["promotion_price_brl"]),
            pix_price_brl=_optional_float(row["pix_price_brl"]),
            current_price_brl=row["current_price_brl"],
        ),
        availability=row["availability"],
        availability_label=AVAILABILITY_LABELS.get(row["availability"], row["availability"]),
        is_sellable=bool(row["is_sellable"]),
        stock_quantity=row["stock_quantity"],
        description=row["description"],
        description_verified=bool(row["description_verified"]),
        specs=json.loads(row["specs"]) if row["specs"] else {},
    )
