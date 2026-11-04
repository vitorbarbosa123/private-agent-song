"""Ferramentas de condições comerciais: formas de pagamento e frete.

Os cálculos usam `emporio.policy_rules`, a mesma fonte usada para validar os pedidos no
pipeline de dados. Assim o agente e os dados seguem exatamente as mesmas regras.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from emporio import policy_rules as rules
from emporio.data.utils import normalize_for_search
from emporio.repository.models import Product
from emporio.tools.context import ToolContext
from emporio.tools.formatting import brl


class _AmountOrProducts(BaseModel):
    product_ids: list[int] | None = Field(
        default=None, description="IDs dos produtos (preferível: considera promoções corretamente)."
    )
    amount: float | None = Field(default=None, gt=0, description="Valor total em R$, se não houver IDs.")


def _load_products(ctx: ToolContext, ids: list[int]) -> tuple[list[Product], list[int]]:
    found, missing = [], []
    for pid in ids:
        product = ctx.repo.get_product(pid)
        (found.append(product) if product else missing.append(pid))
    return found, missing


# --- payment_options ----------------------------------------------------------------


class PaymentOptionsInput(_AmountOrProducts):
    @model_validator(mode="after")
    def _needs_value(self) -> PaymentOptionsInput:
        if not self.product_ids and self.amount is None:
            raise ValueError("Informe 'product_ids' ou 'amount'.")
        return self


class PaymentOptionsResult(BaseModel):
    total: str
    pix: str
    pix_savings: str | None = Field(default=None, description="Quanto o cliente economiza no PIX.")
    pix_note: str
    debit: str
    boleto: str
    credit_max_installments: int
    credit_options: list[str]
    split_payment_allowed: bool
    notes: list[str] = Field(default_factory=list)


def payment_options(ctx: ToolContext, args: PaymentOptionsInput) -> PaymentOptionsResult:
    notes: list[str] = []
    if args.product_ids:
        products, missing = _load_products(ctx, args.product_ids)
        if missing:
            notes.append(f"Produtos inexistentes ignorados: {missing}.")
        total = sum((Decimal(str(p.price.current_price_brl)) for p in products), Decimal("0"))
        # PIX só desconta itens sem promoção (manual 6.2).
        pix_total = sum(
            (Decimal(str(p.price.pix_price_brl if p.price.pix_price_brl is not None else p.price.current_price_brl))
             for p in products),
            Decimal("0"),
        )
        promo_items = [p.name for p in products if p.price.promotion_price_brl is not None]
        if promo_items and len(promo_items) == len(products):
            pix_note = "Sem desconto adicional no PIX: os itens já estão em promoção (não acumula)."
        elif promo_items:
            pix_note = f"5% de desconto no PIX, exceto nos itens em promoção: {', '.join(promo_items)}."
        else:
            pix_note = "5% de desconto no pagamento à vista via PIX."
        if not products:
            raise ValueError("Nenhum dos produtos informados existe.")
    else:
        total = Decimal(str(args.amount))
        pix_total = total * (1 - rules.PIX_DISCOUNT_PERCENT / 100)
        pix_note = ("5% de desconto no PIX sobre o preço de tabela. Se algum item estiver em "
                    "promoção, o desconto do PIX não vale para ele.")

    total, pix_total = rules.round_brl(total), rules.round_brl(pix_total)
    max_n = rules.max_installments_for(total)
    options = [
        f"{n}x de {brl(rules.round_brl(total / n))} sem juros"
        for n in range(1, max_n + 1)
        if rules.is_installment_plan_allowed(total, n)
    ]
    split_allowed = total > rules.SPLIT_PAYMENT_MIN_TOTAL
    if split_allowed:
        notes.append("Compras acima de R$ 2.000,00 podem combinar formas de pagamento (ex.: PIX + cartão).")
    return PaymentOptionsResult(
        total=brl(total),
        pix=brl(pix_total),
        pix_savings=brl(total - pix_total) if pix_total < total else None,
        pix_note=pix_note,
        debit=f"{brl(total)} à vista (todas as bandeiras)",
        boleto=f"{brl(total)} à vista; compensação em até 3 dias úteis",
        credit_max_installments=max_n,
        credit_options=options,
        split_payment_allowed=split_allowed,
        notes=notes,
    )


# --- shipping_quote -----------------------------------------------------------------


class ShippingQuoteInput(_AmountOrProducts):
    city: str = Field(description="Cidade de entrega informada pelo cliente (único campo obrigatório).")


class ShippingQuoteResult(BaseModel):
    region: str
    fee: str | None = None
    delivery_time: str | None = None
    carriers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def shipping_quote(ctx: ToolContext, args: ShippingQuoteInput) -> ShippingQuoteResult:
    notes: list[str] = []
    products: list[Product] = []
    total: Decimal | None = Decimal(str(args.amount)) if args.amount is not None else None
    if args.product_ids:
        products, missing = _load_products(ctx, args.product_ids)
        if missing:
            notes.append(f"Produtos inexistentes ignorados: {missing}.")
        total = sum((Decimal(str(p.price.current_price_brl)) for p in products), Decimal("0"))

    is_metro = normalize_for_search(args.city) in rules.METRO_CITIES
    large_item = any(p.category_id in rules.SPECIAL_FREIGHT_CATEGORY_IDS for p in products)
    # Fora de Campo Grande, o alerta vale mesmo sem produto definido (manual 5.2).
    if large_item or (not is_metro and not products):
        notes.append("Instrumentos de grande porte (baterias, pianos digitais, contrabaixos) podem "
                     "exigir frete especial com cotação individual: confirme com a equipe.")

    if is_metro:
        result = ShippingQuoteResult(
            region="Campo Grande (entrega por motoboy próprio)",
            delivery_time=rules.METRO_DELIVERY_DAYS,
            notes=[*notes, "O cliente recebe uma ligação antes da entrega."],
        )
        if total is None:
            result.notes.append("Frete grátis a partir de R$ 500,00; abaixo disso, taxa fixa de R$ 35,00.")
        else:
            fee = rules.metro_shipping_fee(total)
            result.fee = "grátis" if fee == 0 else brl(fee)
            if fee:
                missing_for_free = rules.FREE_SHIPPING_THRESHOLD - total
                result.notes.append(f"Faltam {brl(missing_for_free)} para o frete grátis (a partir de R$ 500,00).")
        return result

    return ShippingQuoteResult(
        region=f"{args.city} (fora de Campo Grande)",
        carriers=[f"{name}: {days}" for name, days in rules.NATIONAL_CARRIERS],
        notes=[
            *notes,
            "O valor do frete é calculado no checkout pelo CEP, peso e dimensões; não informe valores.",
            "Todos os envios têm rastreamento e seguro contra extravio e avaria.",
        ],
    )
