"""Testes das ferramentas do agente (sem LLM)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime

import pytest

from emporio.business_hours import STORE_TZ
from emporio.repository import StoreRepository
from emporio.tools import TOOL_NAMES, ToolContext, build_tools
from emporio.tools.commerce import PaymentOptionsInput, ShippingQuoteInput, payment_options, shipping_quote
from emporio.tools.orders import (
    OrderCredentials,
    ReturnEligibilityInput,
    check_return_eligibility,
    get_order_status,
)
from emporio.tools.products import (
    GetProductInput,
    SearchProductsInput,
    get_product_details,
    list_categories,
    list_promotions,
    mentions_accessory,
    search_products,
)
from emporio.tools.store import store_status

MakeCtx = Callable[..., ToolContext]

# Credenciais dos pedidos usados nos testes (data/customers.csv).
LETICIA = {"order_id": 7, "email": "leticia.rocha@jmail.com"}  # entregue, previsão 17/02/2026
ANA = {"order_id": 8, "email": "anacarol.ferreira@coldmail.com"}  # enviado, previsão 28/02/2026


@pytest.fixture
def make_ctx(repo: StoreRepository) -> MakeCtx:
    def factory(now: str = "2026-03-02T10:30") -> ToolContext:
        fixed = datetime.fromisoformat(now).replace(tzinfo=STORE_TZ)
        return ToolContext(repo=repo, clock=lambda: fixed)

    return factory


@pytest.fixture
def ctx(make_ctx: MakeCtx) -> ToolContext:
    return make_ctx()


# --- Produtos ------------------------------------------------------------------------


def test_product_price_takamine(ctx: ToolContext) -> None:
    result = get_product_details(ctx, GetProductInput(name="Takamine GD20"))
    assert result.found
    assert result.product.price.list_price == "R$ 2.199,00"
    assert result.product.price.pix_price == "R$ 2.089,05"
    assert result.product.price.pix_savings == "R$ 109,95"
    assert result.product.price.promotion is None  # promoção de 12% inativa


def test_product_ambiguous_name_returns_candidates(ctx: ToolContext) -> None:
    result = get_product_details(ctx, GetProductInput(name="Martin D28"))
    assert not result.found
    assert {c.product_id for c in result.candidates} == {93, 108}


def test_product_out_of_stock_returns_alternatives(ctx: ToolContext) -> None:
    result = get_product_details(ctx, GetProductInput(name="Giannini GF-3D"))
    assert result.found and not result.product.available_for_sale
    assert "esgotado" in result.notes[0]
    assert len(result.alternatives) == 3
    assert all(a.available_for_sale for a in result.alternatives)


@pytest.mark.parametrize(("product_id", "fragment"), [(136, "fora de linha"), (130, "Lançamento")])
def test_product_unavailable_notes(ctx: ToolContext, product_id: int, fragment: str) -> None:
    result = get_product_details(ctx, GetProductInput(product_id=product_id))
    assert fragment in result.notes[0]


def test_product_not_found(ctx: ToolContext) -> None:
    assert not get_product_details(ctx, GetProductInput(product_id=9999)).found
    result = get_product_details(ctx, GetProductInput(name="pedal Boss DS-1"))
    assert not result.found and "acessórios" in result.notes[0]


def test_product_input_requires_identifier() -> None:
    with pytest.raises(ValueError, match="name"):
        GetProductInput()


def test_promotion_is_shown_with_original_price(ctx: ToolContext) -> None:
    product = get_product_details(ctx, GetProductInput(product_id=90)).product
    assert product.price.list_price == "R$ 2.399,00"
    assert product.price.promotion.discount == "18%"
    assert product.price.promotion.price == "R$ 1.967,18"
    assert product.price.promotion.savings == "R$ 431,82"
    assert product.price.pix_price is None  # não acumula


def test_search_guitars_under_1000(ctx: ToolContext) -> None:
    result = search_products(ctx, SearchProductsInput(category="violões", max_price=1000, sort="price_asc"))
    assert result.total_found == 12
    assert len(result.products) == 5  # limite padrão
    assert result.products[0].price.list_price == "R$ 429,90"


@pytest.mark.parametrize(
    "args",
    [
        {"query": "cordas para guitarra"},
        {"category": "amplificador"},
        {"query": "pedal de distorção"},
    ],
)
def test_search_accessories_are_redirected(ctx: ToolContext, args: dict[str, str]) -> None:
    result = search_products(ctx, SearchProductsInput(**args))
    assert result.total_found == 0
    assert "acessórios" in result.notes[0]


def test_search_seven_string_guitar_is_not_an_accessory(ctx: ToolContext) -> None:
    result = search_products(ctx, SearchProductsInput(query="7 cordas"))
    assert result.total_found > 0 and not result.notes


def test_search_unknown_and_empty_categories(ctx: ToolContext) -> None:
    unknown = search_products(ctx, SearchProductsInput(category="drone"))
    assert "não encontrada" in unknown.notes[0] and "Violões" in unknown.notes[0]
    empty = search_products(ctx, SearchProductsInput(category="saxofone"))
    assert empty.total_found == 0 and "não há produtos disponíveis" in empty.notes[0]


def test_search_hints_unavailable_matches(ctx: ToolContext) -> None:
    result = search_products(ctx, SearchProductsInput(query="GF-3D"))
    assert result.total_found == 0
    assert "indisponíveis" in result.notes[0]


def test_mentions_accessory() -> None:
    assert mentions_accessory("caixa de som bluetooth") == "caixa de som"
    assert mentions_accessory("violão", None) is None


def test_list_categories_and_promotions(ctx: ToolContext) -> None:
    categories = {c.name: c.available_products for c in list_categories(ctx).categories}
    assert categories["Cordas Orquestrais"] == 0
    promotions = list_promotions(ctx)
    assert {p.product_id for p in promotions.products} == {90, 94, 121, 127}


# --- Pedidos -------------------------------------------------------------------------


def test_order_status_ok(ctx: ToolContext) -> None:
    result = get_order_status(ctx, OrderCredentials(**ANA))
    assert result.status == "ok"
    order = result.order
    assert order.status == "enviado"
    assert order.tracking_code == "BRJL5544332BR"
    assert order.items == ["1x Kala KA-C Concert Mogno"]
    assert "já passou" in order.notes[0]  # previsão 28/02 < hoje 02/03


def test_order_status_on_time(make_ctx: MakeCtx) -> None:
    result = get_order_status(make_ctx("2026-02-20T10:00"), OrderCredentials(**ANA))
    assert result.order.notes == []


@pytest.mark.parametrize(
    ("creds", "payment", "note"),
    [
        ({"order_id": 16, "email": "camila.duarte@inlook.com"}, "cartão de crédito em 6x de R$ 71,65", "pagamento"),
        ({"order_id": 11, "email": "mariana.costa@inlook.com"}, "boleto bancário", "rastreio"),
        ({"order_id": 17, "email": "matheus.correia@hayoo.com.br"}, "PIX", "cancelado pelo cliente"),
    ],
)
def test_order_status_by_state(ctx: ToolContext, creds: dict, payment: str, note: str) -> None:
    order = get_order_status(ctx, OrderCredentials(**creds)).order
    assert order.payment == payment
    assert note in order.notes[0]


def test_order_requires_verification(ctx: ToolContext) -> None:
    result = get_order_status(ctx, OrderCredentials(order_id=8))
    assert result.status == "verification_required" and result.order is None
    assert ctx.failed_auth_attempts == 0  # pedir dados não conta como tentativa


def test_order_lockout_after_failed_attempts(ctx: ToolContext) -> None:
    for attempt in range(3):
        result = get_order_status(ctx, OrderCredentials(order_id=8, email=f"chute{attempt}@x.com"))
        assert result.status == "not_verified"
        assert "existe" in result.message  # orienta o LLM a não revelar se o pedido existe
    blocked = get_order_status(ctx, OrderCredentials(**ANA))  # mesmo com dados corretos
    assert blocked.status == "blocked" and blocked.order is None


# --- Trocas e devoluções -------------------------------------------------------------


def _returns(ctx: ToolContext, reason: str, creds: dict = LETICIA, **extra: object):
    return check_return_eligibility(ctx, ReturnEligibilityInput(**creds, reason=reason, **extra))


def test_withdrawal_within_7_days(make_ctx: MakeCtx) -> None:
    result = _returns(make_ctx("2026-02-20T10:00"), "arrependimento")
    assert result.eligible is True
    assert result.deadline == "24/02/2026"
    assert result.days_remaining == 4
    assert "previsão de entrega" in result.date_basis
    assert "PREVISÃO" in result.notes[0]
    assert result.requires_human


def test_withdrawal_after_7_days(ctx: ToolContext) -> None:
    result = _returns(ctx, "arrependimento")
    assert result.eligible is False and "terminou em 24/02/2026" in result.decision


def test_withdrawal_uses_customer_received_date(ctx: ToolContext) -> None:
    result = _returns(ctx, "arrependimento", received_date=date(2026, 2, 27))
    assert result.eligible is True and result.deadline == "06/03/2026"
    assert "informada pelo cliente" in result.date_basis
    assert result.notes == []


def test_received_date_in_future_is_rejected(ctx: ToolContext) -> None:
    result = _returns(ctx, "arrependimento", received_date=date(2026, 12, 1))
    assert result.eligible is None and "inconsistente" in result.decision


@pytest.mark.parametrize(
    ("now", "eligible", "fragment"),
    [
        ("2026-03-02T10:00", True, "troca direta"),  # 27 dias da compra
        ("2026-04-15T10:00", True, "garantia legal"),  # > 30 da compra, < 90 do recebimento
        ("2026-06-01T10:00", False, "fabricante"),  # > 90 do recebimento
    ],
)
def test_defect_windows(make_ctx: MakeCtx, now: str, eligible: bool, fragment: str) -> None:
    result = _returns(make_ctx(now), "defeito")
    assert result.eligible is eligible
    assert fragment in result.decision
    assert result.requires_human


def test_returns_by_order_state(ctx: ToolContext) -> None:
    shipped = _returns(ctx, "arrependimento", creds=ANA)
    assert shipped.eligible is None and "em trânsito" in shipped.decision
    pending = _returns(ctx, "arrependimento", creds={"order_id": 13, "email": "fernanda.ribeiro@coldmail.com"})
    assert pending.requires_human and "cancelamento" in pending.decision
    cancelled = _returns(ctx, "defeito", creds={"order_id": 17, "email": "matheus.correia@hayoo.com.br"})
    assert cancelled.eligible is False


def test_returns_require_verification(ctx: ToolContext) -> None:
    result = _returns(ctx, "arrependimento", creds={"order_id": 7})
    assert result.status == "verification_required" and result.eligible is None


# --- Pagamento e frete ---------------------------------------------------------------


def test_payment_options_regular_product(ctx: ToolContext) -> None:
    result = payment_options(ctx, PaymentOptionsInput(product_ids=[95]))
    assert result.pix == "R$ 2.089,05" and result.pix_savings == "R$ 109,95"
    assert result.credit_max_installments == 12
    assert result.credit_options[-1] == "12x de R$ 183,25 sem juros"
    assert result.split_payment_allowed


def test_payment_options_promotional_product_has_no_pix_discount(ctx: ToolContext) -> None:
    result = payment_options(ctx, PaymentOptionsInput(product_ids=[90]))
    assert result.total == result.pix == "R$ 1.967,18"
    assert result.pix_savings is None
    assert "não acumula" in result.pix_note
    assert not result.split_payment_allowed  # 1.967,18 < 2.000


def test_payment_options_mixed_cart(ctx: ToolContext) -> None:
    result = payment_options(ctx, PaymentOptionsInput(product_ids=[90, 95]))
    assert result.total == "R$ 4.166,18"
    assert result.pix == "R$ 4.056,23"  # 1.967,18 (promo) + 2.089,05 (PIX)
    assert "Crafter" in result.pix_note


@pytest.mark.parametrize(("amount", "max_n"), [(349.90, 4), (120.00, 2), (99.00, 1), (1200.00, 12)])
def test_payment_installment_limits(ctx: ToolContext, amount: float, max_n: int) -> None:
    result = payment_options(ctx, PaymentOptionsInput(amount=amount))
    assert result.credit_max_installments == max_n
    assert len(result.credit_options) == max_n


def test_payment_requires_value() -> None:
    with pytest.raises(ValueError):
        PaymentOptionsInput()


@pytest.mark.parametrize(("amount", "fee"), [(500.00, "grátis"), (499.99, "R$ 35,00")])
def test_shipping_campo_grande(ctx: ToolContext, amount: float, fee: str) -> None:
    result = shipping_quote(ctx, ShippingQuoteInput(city="  campo GRANDE ", amount=amount))
    assert result.fee == fee
    assert result.delivery_time == "1 a 3 dias úteis"


def test_shipping_other_city_without_product_warns_about_large_items(ctx: ToolContext) -> None:
    result = shipping_quote(ctx, ShippingQuoteInput(city="Corumbá"))
    assert any("frete especial" in n for n in result.notes)


def test_shipping_other_city_has_no_price(ctx: ToolContext) -> None:
    result = shipping_quote(ctx, ShippingQuoteInput(city="Dourados", product_ids=[140]))
    assert result.fee is None
    assert len(result.carriers) == 3
    assert any("frete especial" in n for n in result.notes)  # bateria acústica


# --- Horário -------------------------------------------------------------------------


def test_store_status_open(ctx: ToolContext) -> None:
    result = store_status(ctx)
    assert result.is_open and result.closes_at == "18:00"
    assert result.now == "segunda-feira, 02/03/2026 10:30"


def test_store_status_closed_saturday_afternoon(make_ctx: MakeCtx) -> None:
    result = store_status(make_ctx("2026-03-07T14:00"))
    assert not result.is_open
    assert result.next_opening == "segunda-feira (09/03) às 09:00"


def test_store_status_holiday(make_ctx: MakeCtx) -> None:
    result = store_status(make_ctx("2026-04-03T10:00"))
    assert not result.is_open and "Sexta-feira Santa" in result.today
    assert result.next_opening == "amanhã às 09:00"


# --- Registro LangChain --------------------------------------------------------------


def test_registry_exposes_all_tools(ctx: ToolContext) -> None:
    tools = build_tools(ctx)
    assert [t.name for t in tools] == list(TOOL_NAMES)
    assert len(set(TOOL_NAMES)) == len(TOOL_NAMES) == 11
    for tool in tools:
        assert len(tool.description) > 40


def test_registry_returns_json(ctx: ToolContext) -> None:
    tools = {t.name: t for t in build_tools(ctx)}
    payload = json.loads(tools["get_product_details"].invoke({"name": "Takamine GD20"}))
    assert payload["product"]["product_id"] == 95
    assert "candidates" in payload  # listas vazias são mantidas; só None é omitido


def test_registry_turns_errors_into_messages(ctx: ToolContext) -> None:
    tools = {t.name: t for t in build_tools(ctx)}
    message = tools["payment_options"].invoke({})
    assert isinstance(message, str) and "Parâmetros inválidos" in message


def test_registry_turns_runtime_errors_into_messages(ctx: ToolContext) -> None:
    """Erros dentro da ferramenta (não só de validação) também viram mensagem."""
    tools = {t.name: t for t in build_tools(ctx)}
    message = tools["payment_options"].invoke({"product_ids": [9999]})
    assert message.startswith("Erro ao executar payment_options") and "Nenhum dos produtos" in message
