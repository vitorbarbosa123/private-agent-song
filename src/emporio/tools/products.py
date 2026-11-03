"""Ferramentas de catálogo: busca, detalhes de produto, categorias e promoções."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from emporio.data.products import SPEC_LABELS
from emporio.data.utils import normalize_for_search
from emporio.policy_rules import ACCESSORY_KEYWORDS
from emporio.repository.models import Product
from emporio.tools.context import ToolContext
from emporio.tools.formatting import brl, percent

AMBIGUITY_MARGIN = 1.0  # pontos de similaridade abaixo dos quais dois produtos "empatam"
CONFIDENT_MATCH = 90.0
LOW_STOCK = 2

ACCESSORY_NOTE = (
    "A Empório da Música trabalha exclusivamente com instrumentos musicais e não vende "
    "acessórios (cordas, palhetas, cabos, cases, pedais, amplificadores etc.). Redirecione o "
    "cliente com educação e sugira procurar uma loja especializada em acessórios."
)

# --- Visões retornadas ao LLM ------------------------------------------------------


class PromotionView(BaseModel):
    name: str | None
    discount: str
    price: str


class PriceView(BaseModel):
    list_price: str = Field(description="Preço de tabela.")
    promotion: PromotionView | None = Field(
        default=None, description="Promoção vigente. Mostrar junto do preço original e do percentual."
    )
    pix_price: str | None = Field(
        default=None, description="Preço à vista no PIX (5% off). Ausente quando há promoção: não acumulam."
    )
    current_price_brl: float = Field(description="Preço vigente numérico, para outras ferramentas.")


class ProductView(BaseModel):
    product_id: int
    name: str
    brand: str | None
    category: str
    availability: str
    available_for_sale: bool
    stock_note: str | None = None
    price: PriceView
    description: str | None
    specs: dict[str, str]


def _spec_value(value: object) -> str:
    if value is True:
        return "sim"
    if value is False:
        return "não"
    return str(value)


def product_view(p: Product) -> ProductView:
    promo = None
    if p.price.promotion_price_brl is not None and p.price.promotion_discount_percent is not None:
        promo = PromotionView(
            name=p.price.promotion_name,
            discount=percent(p.price.promotion_discount_percent),
            price=brl(p.price.promotion_price_brl),
        )
    stock_note = None
    if p.is_sellable and p.stock_quantity <= LOW_STOCK:
        stock_note = f"últimas {p.stock_quantity} unidades" if p.stock_quantity > 1 else "última unidade"
    return ProductView(
        product_id=p.product_id,
        name=p.name,
        brand=p.brand,
        category=p.category_name,
        availability=p.availability_label,
        available_for_sale=p.is_sellable,
        stock_note=stock_note,
        price=PriceView(
            list_price=brl(p.price.list_price_brl),
            promotion=promo,
            pix_price=brl(p.price.pix_price_brl) if p.price.pix_price_brl is not None else None,
            current_price_brl=p.price.current_price_brl,
        ),
        description=p.description,
        specs={SPEC_LABELS.get(k, k): _spec_value(v) for k, v in p.specs.items()},
    )


def mentions_accessory(*texts: str | None) -> str | None:
    """Retorna o acessório citado, se houver ('cordas', 'pedal', 'caixa de som'...)."""
    for text in texts:
        normalized = normalize_for_search(text)
        words = set(normalized.split())
        for keyword in ACCESSORY_KEYWORDS:
            if (" " in keyword and keyword in normalized) or keyword in words:
                return keyword
    return None


# --- search_products ----------------------------------------------------------------


class SearchProductsInput(BaseModel):
    query: str | None = Field(
        default=None,
        description="Texto livre: marca, modelo ou tipo (ex.: 'Yamaha', 'dreadnought', 'tenor').",
    )
    category: str | None = Field(
        default=None, description="Categoria em linguagem natural (ex.: 'violão', 'guitarra', 'ukulele')."
    )
    min_price: float | None = Field(default=None, ge=0, description="Preço mínimo em R$.")
    max_price: float | None = Field(default=None, ge=0, description="Preço máximo em R$ (considera promoções).")
    brand: str | None = Field(default=None, description="Marca exata (ex.: 'Fender').")
    string_type: Literal["nylon", "aço"] | None = Field(default=None, description="Tipo de corda.")
    has_electronics: bool | None = Field(default=None, description="True = com captação/eletroacústico.")
    include_unavailable: bool = Field(
        default=False, description="Incluir esgotados, fora de linha e lançamentos futuros."
    )
    sort: Literal["relevance", "price_asc", "price_desc"] = "relevance"
    limit: int = Field(default=5, ge=1, le=10)


class SearchProductsResult(BaseModel):
    total_found: int
    products: list[ProductView]
    notes: list[str] = Field(default_factory=list)


def search_products(ctx: ToolContext, args: SearchProductsInput) -> SearchProductsResult:
    notes: list[str] = []
    category_id = None
    if args.category:
        category = ctx.repo.resolve_category(args.category)
        if category is None:
            accessory = mentions_accessory(args.category, args.query)
            if accessory:
                return SearchProductsResult(total_found=0, products=[], notes=[ACCESSORY_NOTE])
            names = ", ".join(c.name for c in ctx.repo.list_categories())
            return SearchProductsResult(
                total_found=0, products=[],
                notes=[f"Categoria '{args.category}' não encontrada. Categorias da loja: {names}."],
            )
        category_id = category.category_id
        if category.sellable_count == 0 and not args.include_unavailable:
            notes.append(
                f"No momento não há produtos disponíveis na categoria '{category.name}'. Ofereça "
                "contato com a equipe para encomendas."
            )

    filters = dict(
        text=args.query, category_id=category_id, min_price=args.min_price, max_price=args.max_price,
        brand=args.brand, string_type=args.string_type, has_electronics=args.has_electronics,
        sort=args.sort,
    )
    matches = ctx.repo.search_products(**filters, only_available=not args.include_unavailable, limit=100)

    if not matches:
        if accessory := mentions_accessory(args.query, args.category):
            notes.append(ACCESSORY_NOTE)
        elif not args.include_unavailable:
            unavailable = ctx.repo.search_products(**filters, only_available=False, limit=100)
            if unavailable:
                notes.append(
                    f"{len(unavailable)} produto(s) atendem à busca, mas estão indisponíveis. "
                    "Use include_unavailable=true para vê-los e sugerir alternativas."
                )
    return SearchProductsResult(
        total_found=len(matches),
        products=[product_view(m.product) for m in matches[: args.limit]],
        notes=notes,
    )


# --- get_product_details ------------------------------------------------------------


class GetProductInput(BaseModel):
    name: str | None = Field(default=None, description="Nome ou modelo citado pelo cliente (ex.: 'Takamine GD20').")
    product_id: int | None = Field(default=None, description="ID do produto, se já conhecido.")

    @model_validator(mode="after")
    def _one_identifier(self) -> GetProductInput:
        if not self.name and self.product_id is None:
            raise ValueError("Informe 'name' ou 'product_id'.")
        return self


class GetProductResult(BaseModel):
    found: bool
    product: ProductView | None = None
    candidates: list[ProductView] = Field(
        default_factory=list, description="Quando a busca é ambígua: pergunte ao cliente qual deles."
    )
    alternatives: list[ProductView] = Field(
        default_factory=list, description="Opções disponíveis parecidas, quando o produto não está à venda."
    )
    notes: list[str] = Field(default_factory=list)


_UNAVAILABLE_NOTES = {
    "out_of_stock": "Produto temporariamente esgotado. Não confirme prazo de reposição; ofereça as alternativas.",
    "discontinued": "Produto fora de linha: não faz mais parte do catálogo. Ofereça modelos equivalentes.",
    "coming_soon": "Lançamento em breve, ainda não disponível para venda. Ofereça as alternativas.",
    "unknown": "Produto indisponível para venda no momento.",
}


def get_product_details(ctx: ToolContext, args: GetProductInput) -> GetProductResult:
    if args.product_id is not None:
        product = ctx.repo.get_product(args.product_id)
        if product is None:
            return GetProductResult(found=False, notes=[f"Produto {args.product_id} não existe."])
    else:
        matches = ctx.repo.find_products_by_name(args.name or "", limit=5)
        confident = [m for m in matches if m.score >= CONFIDENT_MATCH]
        if not confident:
            notes = ["Nenhum produto com esse nome no catálogo."]
            if accessory := mentions_accessory(args.name):
                notes = [ACCESSORY_NOTE]
            elif matches:
                notes.append("Há nomes parecidos em 'candidates'; confirme com o cliente.")
            return GetProductResult(
                found=False, candidates=[product_view(m.product) for m in matches], notes=notes
            )
        tied = [m for m in confident if confident[0].score - m.score < AMBIGUITY_MARGIN]
        if len(tied) > 1:
            return GetProductResult(
                found=False,
                candidates=[product_view(m.product) for m in tied],
                notes=["Mais de um produto corresponde ao nome. Pergunte ao cliente qual deles."],
            )
        product = confident[0].product

    notes: list[str] = []
    alternatives: list[ProductView] = []
    if not product.is_sellable:
        notes.append(_UNAVAILABLE_NOTES.get(product.availability, _UNAVAILABLE_NOTES["unknown"]))
        alternatives = [product_view(p) for p in ctx.repo.find_alternatives(product)]
    return GetProductResult(found=True, product=product_view(product), alternatives=alternatives, notes=notes)


# --- list_categories / list_promotions -----------------------------------------------


class NoInput(BaseModel):
    pass


class CategoryView(BaseModel):
    name: str
    description: str | None
    available_products: int


class ListCategoriesResult(BaseModel):
    categories: list[CategoryView]
    notes: list[str]


def list_categories(ctx: ToolContext, _: NoInput | None = None) -> ListCategoriesResult:
    return ListCategoriesResult(
        categories=[
            CategoryView(name=c.name, description=c.description, available_products=c.sellable_count)
            for c in ctx.repo.list_categories()
        ],
        notes=["A loja vende somente instrumentos musicais (sem acessórios)."],
    )


class ListPromotionsResult(BaseModel):
    products: list[ProductView]
    notes: list[str]


def list_promotions(ctx: ToolContext, _: NoInput | None = None) -> ListPromotionsResult:
    return ListPromotionsResult(
        products=[product_view(p.product) for p in ctx.repo.list_active_promotions()],
        notes=[
            "Apresente sempre o preço original, o percentual e o preço promocional (manual 6.2).",
            "Promoções não são cumulativas: o desconto do PIX não vale sobre preço promocional.",
        ],
    )
