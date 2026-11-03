"""Testes da camada de dados (consultas fixas sobre o SQLite tratado)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from emporio.repository import DatabaseNotFoundError, StoreRepository
from emporio.repository.repository import text_score

# --- Busca textual -------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("takamine gd20", "Takamine GD20 Dreadnought Natural"),
        ("martin d28", "Martin D-28 Dreadnought Natural"),  # hífen
        ("violão", "Yamaha C40 Nylon Natural Violões"),  # plural e acento
        ("yamha", "Yamaha F310 Aço Natural"),  # erro de digitação
    ],
)
def test_text_score_full_match(query: str, document: str) -> None:
    assert text_score(query, document) >= 90


@pytest.mark.parametrize(
    ("query", "document"),
    [
        ("violino", "Yamaha C40 Nylon Natural Violões"),
        ("pedal", "Bateria Acústica Pearl Kit 2 Studio"),
        ("", "qualquer coisa"),
    ],
)
def test_text_score_no_match(query: str, document: str) -> None:
    assert text_score(query, document) == 0


# --- Categorias ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("violão", "Violões"),
        ("violoes", "Violões"),
        ("baixo", "Baixos"),  # não "Cordas Orquestrais" (contrabaixos)
        ("violino", "Cordas Orquestrais"),
        ("sax", "Instrumentos de Sopro (Madeiras)"),
        ("piano", "Teclados e Pianos"),
        ("pedal", None),  # acessório: a loja não vende
        ("amplificador", None),
    ],
)
def test_resolve_category(repo: StoreRepository, text: str, expected: str | None) -> None:
    category = repo.resolve_category(text)
    assert (category.name if category else None) == expected


def test_empty_categories_are_listed(repo: StoreRepository) -> None:
    empty = {c.category_id for c in repo.list_categories() if c.product_count == 0}
    assert empty == {6, 7, 8}


# --- Produtos ------------------------------------------------------------------


def test_find_product_by_name_takamine(repo: StoreRepository) -> None:
    """Cenário do enunciado: 'Quanto custa o Takamine GD20?'."""
    best = repo.find_products_by_name("Takamine GD 20")[0]
    assert best.product.product_id == 95
    price = best.product.price
    assert price.list_price_brl == 2199
    assert price.promotion_price_brl is None  # promoção de 12% está inativa
    assert price.pix_price_brl == pytest.approx(2089.05)


def test_find_by_name_includes_unavailable(repo: StoreRepository) -> None:
    best = repo.find_products_by_name("Giannini GF-3D")[0].product
    assert best.product_id == 96
    assert best.availability == "out_of_stock"
    assert best.availability_label == "esgotado no momento"


def test_find_by_name_unknown(repo: StoreRepository) -> None:
    assert repo.find_products_by_name("pedal boss DS-1") == []


def test_search_guitars_under_1000(repo: StoreRepository) -> None:
    """Cenário do enunciado: 'violões disponíveis custando até R$1000'."""
    category = repo.resolve_category("violões")
    results = repo.search_products(category_id=category.category_id, max_price=1000, limit=50)
    ids = [m.product.product_id for m in results]
    assert set(ids) == {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112}
    prices = [m.product.price.current_price_brl for m in results]
    assert prices == sorted(prices)  # sem texto: ordenado por preço


def test_search_includes_unavailable_when_asked(repo: StoreRepository) -> None:
    ids = {m.product.product_id for m in repo.search_products(category_id=5, only_available=False, limit=100)}
    assert {96, 113} <= ids


def test_price_filter_uses_promotional_price(repo: StoreRepository) -> None:
    # Crafter HT-100: tabela R$ 2.399, promoção 18% -> R$ 1.967,18.
    ids = {m.product.product_id for m in repo.search_products(max_price=2000, category_id=5, limit=100)}
    assert 90 in ids


def test_search_by_specs(repo: StoreRepository) -> None:
    results = repo.search_products(category_id=5, string_type="nylon", has_electronics=True, limit=50)
    assert results
    for match in results:
        assert match.product.specs["string_type"] == "nylon"
        assert match.product.specs["electronics"] is True


def test_search_by_brand_is_case_insensitive(repo: StoreRepository) -> None:
    results = repo.search_products(brand="music man", limit=50)
    assert {m.product.product_id for m in results} == {135, 138}


def test_text_search_ranks_full_matches_first(repo: StoreRepository) -> None:
    results = repo.search_products(text="violao eletrico nylon", limit=20)
    top = results[0].product
    assert top.specs.get("string_type") == "nylon" and top.specs.get("electronics") is True


def test_search_is_safe_against_sql_injection(repo: StoreRepository) -> None:
    assert repo.search_products(text="'; DROP TABLE products; --") == []
    assert repo.search_products(brand="x' OR '1'='1") == []
    assert repo.get_product(95) is not None


def test_alternatives_for_out_of_stock(repo: StoreRepository) -> None:
    original = repo.get_product(96)
    alternatives = repo.find_alternatives(original)
    assert len(alternatives) == 3
    assert all(a.is_sellable and a.category_id == original.category_id for a in alternatives)
    assert original.product_id not in {a.product_id for a in alternatives}


def test_conflicting_description_is_not_exposed(repo: StoreRepository) -> None:
    product = repo.get_product(135)
    assert not product.description_verified
    assert "Fender" not in (product.description or "")


def test_active_promotions(repo: StoreRepository) -> None:
    promotions = repo.list_active_promotions()
    assert {p.product.product_id for p in promotions} == {90, 94, 121, 127}
    discounts = [p.discount_percent for p in promotions]
    assert discounts == sorted(discounts, reverse=True)


# --- Pedidos -------------------------------------------------------------------


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": "anacarol.ferreira@coldmail.com"},
        {"email": "  AnaCarol.Ferreira@COLDMAIL.com "},
        {"phone": "(67) 99654-7821"},
        {"phone": "+55 67 996547821"},
        {"email": "anacarol.ferreira@coldmail.com", "phone": "67996547821"},
    ],
)
def test_get_order_authenticated(repo: StoreRepository, credentials: dict[str, str]) -> None:
    order = repo.get_order(8, **credentials)
    assert order is not None
    assert order.status == "shipped"
    assert order.tracking_code == "BRJL5544332BR"
    assert order.customer_first_name == "Ana"
    assert [i.product_name for i in order.items] == ["Kala KA-C Concert Mogno"]


@pytest.mark.parametrize(
    ("order_id", "credentials"),
    [
        (8, {}),  # sem credenciais
        (8, {"email": "outra.pessoa@jmail.com"}),  # e-mail de outro cliente
        (8, {"email": "anacarol.ferreira@coldmail.com", "phone": "67999999999"}),  # telefone não confere
        (999, {"email": "anacarol.ferreira@coldmail.com"}),  # pedido inexistente
    ],
)
def test_get_order_denied(repo: StoreRepository, order_id: int, credentials: dict[str, str]) -> None:
    assert repo.get_order(order_id, **credentials) is None


def test_get_order_does_not_expose_contact_data(repo: StoreRepository) -> None:
    order = repo.get_order(8, email="anacarol.ferreira@coldmail.com")
    dumped = order.model_dump_json()
    assert "coldmail" not in dumped and "99654" not in dumped


def test_shared_email_only_unlocks_own_orders(repo: StoreRepository) -> None:
    # Clientes 11 e 43 compartilham o e-mail; o pedido 10 é do cliente 11.
    assert repo.get_order(10, email="bruno.martins@jmail.com") is not None
    assert repo.get_order(10, phone="(67) 99456-3456") is None  # telefone do cliente 43


# --- Conexão ---------------------------------------------------------------------


def test_connection_is_read_only(repo: StoreRepository) -> None:
    with pytest.raises(sqlite3.OperationalError):
        repo._conn.execute("DELETE FROM products")


def test_missing_database(tmp_path: Path) -> None:
    with pytest.raises(DatabaseNotFoundError):
        StoreRepository(tmp_path / "nao-existe.db")
