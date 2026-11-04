"""Modelos de domínio retornados pelo repositório (e, depois, pelas ferramentas do agente)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

Availability = Literal["in_stock", "out_of_stock", "discontinued", "coming_soon", "unknown"]
OrderStatus = Literal["pending", "confirmed", "shipped", "delivered", "cancelled"]

AVAILABILITY_LABELS: dict[str, str] = {
    "in_stock": "disponível",
    "out_of_stock": "esgotado no momento",
    "discontinued": "fora de linha",
    "coming_soon": "em breve",
    "unknown": "indisponível",
}
ORDER_STATUS_LABELS: dict[str, str] = {
    "pending": "aguardando confirmação do pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


class Price(BaseModel):
    list_price_brl: float = Field(description="Preço de tabela.")
    promotion_name: str | None = None
    promotion_discount_percent: float | None = None
    promotion_price_brl: float | None = None
    pix_price_brl: float | None = Field(
        default=None, description="Preço à vista no PIX (5%). Nulo se há promoção: não acumulam."
    )
    current_price_brl: float = Field(description="Preço vigente: promocional, se houver, senão o de tabela.")


class Product(BaseModel):
    product_id: int
    name: str
    brand: str | None
    category_id: int
    category_name: str
    price: Price
    availability: Availability
    availability_label: str
    is_sellable: bool
    stock_quantity: int
    description: str | None
    description_verified: bool
    specs: dict[str, Any]


class ProductMatch(BaseModel):
    product: Product
    score: float = Field(description="Similaridade com o texto buscado (0-100).")


class Category(BaseModel):
    category_id: int
    name: str
    description: str | None
    product_count: int
    sellable_count: int


class Promotion(BaseModel):
    promotion_id: int
    name: str | None
    discount_percent: float
    product: Product


class OrderItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int


class Order(BaseModel):
    order_id: int
    customer_first_name: str
    order_date: date
    status: OrderStatus
    status_label: str
    total_brl: float
    payment_type: str | None
    installments: int | None
    installment_value_brl: float | None
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: list[OrderItem]
