"""Testes do pipeline de tratamento de dados."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pandas as pd
import pytest

from emporio import policy_rules
from emporio.data.issues import IssueLog
from emporio.data.orders import parse_payment_method
from emporio.data.pipeline import CleanData, run_pipeline, write_outputs
from emporio.data.policies import split_sections
from emporio.data.products import (
    brands_in,
    classify_availability,
    find_description_conflicts,
    normalize_specs,
)
from emporio.data.utils import format_brl, normalize_for_search

# --- Regras de negócio --------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "installments", "allowed"),
    [
        (159.90, 3, True),  # 53,30 >= 50
        (120.00, 3, False),  # 40,00 < 50
        (349.90, 6, False),  # 58,32 < 80 (pedido 9)
        (480.00, 6, True),  # 80,00 == 80
        (459.90, 12, False),  # 38,33 < 100 (pedido 18)
        (1200.00, 12, True),
        (10.00, 1, True),  # à vista sempre permitido
        (5000.00, 13, False),  # acima do máximo
    ],
)
def test_installment_rules(total: float, installments: int, allowed: bool) -> None:
    assert policy_rules.is_installment_plan_allowed(total, installments) is allowed


def test_max_installments_for() -> None:
    assert policy_rules.max_installments_for(349.90) == 4  # 87,48 >= 80; 5x = 69,98
    assert policy_rules.max_installments_for(2199) == 12


def test_free_shipping_threshold_is_inclusive() -> None:
    assert policy_rules.metro_shipping_fee(500) == Decimal("0.00")
    assert policy_rules.metro_shipping_fee(499.99) == Decimal("35.00")


# --- Funções de tratamento ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pix", ("pix", 1)),
        ("credit_12x", ("credit", 12)),
        ("CREDIT_3X", ("credit", 3)),
        ("pix_3x", (None, None)),
        ("cheque", (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_payment_method(raw: str, expected: tuple[str | None, int | None]) -> None:
    assert parse_payment_method(raw) == expected


def test_normalize_for_search_removes_accents() -> None:
    assert normalize_for_search("  Violão   Elétrico​ ") == "violao eletrico"


def test_format_brl() -> None:
    assert format_brl(1234.5) == "R$ 1.234,50"


def test_brands_detected_by_model_hint() -> None:
    assert brands_in("Contrabaixo Precision de 4 cordas") == {"fender"}
    assert brands_in("Ukulele Kalani KAL-300S") == {"kalani"}  # 'kala' não casa com 'kalani'


def test_description_conflict_detects_brand_and_specs() -> None:
    reasons = find_description_conflicts(
        "Yamaha Bass 3X Electric Bass",
        "Contrabaixo ativo de 5 cordas Ibanez com equalizador.",
        {"string_count": 4},
    )
    assert len(reasons) == 2


def test_description_without_conflict() -> None:
    assert find_description_conflicts("Martin D-28 Natural", "Lendário violão Martin D-28.", {}) == []


def test_specs_strings_split_by_semantics() -> None:
    log = IssueLog()
    assert normalize_specs('{"strings": "nylon"}', log=log, record_id=1) == {"string_type": "nylon"}
    assert normalize_specs('{"strings": "6"}', log=log, record_id=2) == {"string_count": 6}
    assert normalize_specs('{"electronics": "yes"}', log=log, record_id=3) == {"electronics": True}
    assert normalize_specs("{quebrado", log=log, record_id=4) == {}
    assert log.record_ids("invalid_specs_json") == {"4"}


@pytest.mark.parametrize(
    ("status", "stock", "expected"),
    [
        ("active", 3, "in_stock"),
        ("active", 0, "out_of_stock"),
        ("discontinued", 13, "discontinued"),
        ("coming_soon", 2, "coming_soon"),
        (None, 5, "unknown"),
    ],
)
def test_classify_availability(status: str | None, stock: int, expected: str) -> None:
    assert classify_availability(status, stock) == expected


def test_split_sections_ignores_numbered_lists() -> None:
    lines = ["1. Sobre", "texto", "1.1 Missão", "missão", "2. Fluxo", "1. Saudação: oi", "3. Fim"]
    sections = split_sections(lines)
    assert [s.section_id for s in sections] == ["0", "1", "1.1", "2", "3"]
    assert "1. Saudação" in sections[3].text


# --- Integração com os dados reais -------------------------------------------


@pytest.fixture(scope="module")
def data() -> CleanData:
    return run_pipeline()


def _ids(data: CleanData, rule: str) -> set[str]:
    return data.log.record_ids(rule)


def test_no_errors_on_real_data(data: CleanData) -> None:
    errors = data.log.to_frame().query("severity == 'error'")
    assert errors.empty, errors.to_string()


def test_known_product_issues(data: CleanData) -> None:
    assert _ids(data, "description_conflict") == {"135", "136", "137", "139", "140", "142", "144"}
    assert _ids(data, "discontinued_with_stock") == {"136"}
    assert _ids(data, "coming_soon_with_stock") == {"130"}
    assert _ids(data, "out_of_stock") == {"96"}
    assert _ids(data, "name_typo") == {"84"}


def test_conflicting_description_is_preserved(data: CleanData) -> None:
    p = data.tables["products"].set_index("product_id")
    assert "Fender" in p.loc[135, "description_original"]
    assert "Fender" not in p.loc[135, "description"]
    assert not p.loc[135, "description_verified"]


def test_pricing_rules(data: CleanData) -> None:
    p = data.tables["products"].set_index("product_id")
    # Takamine GD20: promoção 12% inativa não pode ser aplicada; PIX 5% vale.
    assert pd.isna(p.loc[95, "promotion_id"])
    assert p.loc[95, "pix_price_brl"] == pytest.approx(2089.05)
    # Crafter HT-100: promoção ativa de 18%; PIX não acumula.
    assert p.loc[90, "promotion_price_brl"] == pytest.approx(1967.18)
    assert pd.isna(p.loc[90, "pix_price_brl"])
    assert set(p[p["promotion_id"].notna()].index) == {90, 94, 121, 127}


def test_sellable_guitars_under_1000(data: CleanData) -> None:
    """Cenário do enunciado: 'violões disponíveis custando até R$ 1000'."""
    p = data.tables["products"]
    result = p[(p["category_id"] == 5) & p["is_sellable"] & (p["price_brl"] <= 1000)]
    assert 96 not in set(result["product_id"])  # esgotado
    assert 113 not in set(result["product_id"])  # descontinuado
    assert set(result["product_id"]) == {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112}


def test_known_order_issues(data: CleanData) -> None:
    assert _ids(data, "total_mismatch") == {"3", "20"}
    assert _ids(data, "installment_policy_violation") == {"9", "16", "18"}
    assert _ids(data, "coming_soon_product_sold") == {"3/130", "14/130"}
    orders = data.tables["orders"].set_index("order_id")
    assert orders.loc[3, "total_brl"] == 3450  # total cobrado não é alterado


def test_known_customer_and_category_issues(data: CleanData) -> None:
    assert _ids(data, "shared_email") == {"11, 43"}
    assert _ids(data, "empty_category") == {"6", "7", "8"}


def test_policy_sections_and_contacts(data: CleanData) -> None:
    ids = [s["section_id"] for s in data.policy_sections]
    assert ids[:4] == ["0", "1", "1.1", "1.2"]
    assert "10" in ids and "7.3" in ids
    assert data.log.by_rule("conflicting_phones")
    assert data.log.by_rule("conflicting_emails")
    assert "• |" not in data.policies_markdown


def test_write_outputs(data: CleanData, tmp_path) -> None:
    write_outputs(data, tmp_path)
    with sqlite3.connect(tmp_path / "emporio.db") as conn:
        n = conn.execute("SELECT COUNT(*) FROM products WHERE is_sellable").fetchone()[0]
    assert n == int(data.tables["products"]["is_sellable"].sum())
    facts = json.loads((tmp_path / "store_facts.json").read_text(encoding="utf-8"))
    assert facts["store"]["phone_whatsapp"] == "(67) 3341-4444"
    assert (tmp_path / "data_quality_report.md").exists()
