"""Regras de negócio canônicas, extraídas do manual de políticas (v2.1, jun/2025).

O manual tem trechos ambíguos ou contraditórios. Este módulo é a fonte única da
verdade para as regras *computáveis* (pagamento, frete, prazos) e documenta, em
`RESOLUTIONS`, qual interpretação adotamos para cada conflito e por quê. Ele é
usado pelo pipeline de dados (validação de pedidos) e será usado pelo agente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

# --- Pagamento (seção 3) ----------------------------------------------------

PIX_DISCOUNT_PERCENT = Decimal("5")
MAX_INSTALLMENTS = 12
# (até N parcelas, valor mínimo de cada parcela) — seção 3.1, mais específica que a tabela da seção 3.
INSTALLMENT_TIERS: tuple[tuple[int, Decimal], ...] = (
    (3, Decimal("50.00")),
    (6, Decimal("80.00")),
    (12, Decimal("100.00")),
)
SPLIT_PAYMENT_MIN_TOTAL = Decimal("2000.00")  # PIX + cartão só "acima de" R$ 2.000
PAYMENT_TYPES = ("pix", "debit", "credit", "boleto")

# --- Frete (seção 5) ---------------------------------------------------------

FREE_SHIPPING_THRESHOLD = Decimal("500.00")  # >= 500 → grátis (ver RESOLUTIONS)
METRO_SHIPPING_FEE = Decimal("35.00")
METRO_DELIVERY_DAYS = "1 a 3 dias úteis"
# Municípios atendidos pelo motoboy próprio (ver RESOLUTIONS: "Região metropolitana").
METRO_CITIES = frozenset({"campo grande"})
NATIONAL_CARRIERS: tuple[tuple[str, str], ...] = (
    ("PAC (Correios)", "5 a 12 dias úteis"),
    ("SEDEX (Correios)", "2 a 5 dias úteis"),
    ("Jadlog (.package)", "3 a 8 dias úteis"),
)
# Categorias com "instrumentos de grande porte" que podem exigir frete especial (5.2).
SPECIAL_FREIGHT_CATEGORY_IDS = frozenset({3, 4, 8})  # baterias, teclados/pianos, cordas orquestrais (contrabaixo)

# Acessórios que a loja NÃO vende (1 e 7.1). Usado para redirecionar o cliente.
ACCESSORY_KEYWORDS = frozenset({
    "corda", "cordas", "encordoamento", "palheta", "palhetas", "cabo", "cabos", "case", "cases",
    "bag", "capa", "pedal", "pedais", "pedaleira", "amplificador", "amplificadores", "amp",
    "caixa de som", "afinador", "metronomo", "estante", "suporte", "baqueta", "baquetas",
    "correia", "capotraste", "microfone",
})

# --- Prazos (seções 4 e 8) ---------------------------------------------------

WITHDRAWAL_DAYS = 7  # arrependimento, compras online, a partir do recebimento
PREFERENCE_EXCHANGE_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30  # troca direta na loja, a partir da compra
LEGAL_WARRANTY_DAYS = 90  # garantia legal (CDC), a partir do recebimento


def round_brl(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def min_installment_value(installments: int) -> Decimal | None:
    """Valor mínimo de cada parcela; `None` se o número de parcelas não é permitido."""
    if installments < 1 or installments > MAX_INSTALLMENTS:
        return None
    if installments == 1:
        return Decimal("0")
    for max_n, min_value in INSTALLMENT_TIERS:
        if installments <= max_n:
            return min_value
    return None  # inalcançável enquanto o último tier for MAX_INSTALLMENTS


def is_installment_plan_allowed(total: Decimal | float, installments: int) -> bool:
    minimum = min_installment_value(installments)
    if minimum is None:
        return False
    return round_brl(Decimal(str(total)) / installments) >= minimum


def max_installments_for(total: Decimal | float) -> int:
    """Maior número de parcelas sem juros permitido para um valor total."""
    return max(
        (n for n in range(1, MAX_INSTALLMENTS + 1) if is_installment_plan_allowed(total, n)),
        default=1,
    )


def metro_shipping_fee(order_total: Decimal | float) -> Decimal:
    """Frete na região metropolitana de Campo Grande (seção 5.1)."""
    if Decimal(str(order_total)) >= FREE_SHIPPING_THRESHOLD:
        return Decimal("0.00")
    return METRO_SHIPPING_FEE


# --- Dados institucionais canônicos -----------------------------------------

STORE_INFO: dict[str, object] = {
    "name": "Empório da Música",
    "legal_name": "Empório da Música Instrumentos Musicais Ltda.",
    "cnpj": "12.345.678/0001-90",
    "slogan": "Sua música começa aqui.",
    "founded": 2008,
    "address": "Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333",
    "phone_whatsapp": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
    "business_hours": {
        "monday_to_friday": "09:00-18:00",
        "saturday": "09:00-13:00",
        "sunday_and_holidays": "closed",
    },
    "timezone": "America/Campo_Grande",
    "sells_accessories": False,
}


# --- Conflitos e ambiguidades do manual -------------------------------------


@dataclass(frozen=True)
class PolicyResolution:
    topic: str
    sections: str
    conflict: str
    decision: str
    rationale: str


RESOLUTIONS: tuple[PolicyResolution, ...] = (
    PolicyResolution(
        topic="Telefone / WhatsApp",
        sections="Capa, 1.2 e 7",
        conflict="Capa e 1.2 informam (67) 3341-4444 como 'Telefone / WhatsApp'; a seção 7 "
        "informa o WhatsApp (67) 3321-4500.",
        decision="Número canônico: (67) 3341-4444. O agente não informa o (67) 3321-4500.",
        rationale="Aparece duas vezes, inclusive na tabela de dados cadastrais da empresa, que é "
        "a fonte mais 'oficial' do documento. Divergência a confirmar com a loja.",
    ),
    PolicyResolution(
        topic="E-mail",
        sections="Capa e 1.2",
        conflict="'contato@emporiodamusica.com.br' (capa) vs 'contato@empóriodamusica.com.br' "
        "(1.2, com acento).",
        decision="E-mail canônico sem acento: contato@emporiodamusica.com.br.",
        rationale="Domínios com acento (IDN) são raros e propensos a erro de digitação; a versão "
        "com acento é quase certamente um erro de autocorreção.",
    ),
    PolicyResolution(
        topic="Parcela mínima no cartão de crédito",
        sections="3 e 3.1",
        conflict="A tabela da seção 3 diz 'parcela mínima de R$ 100,00'; a seção 3.1 define "
        "faixas (até 3x, 4x-6x: R$ 80, 7x-12x: R$ 100).",
        decision="Vale a seção 3.1 (faixas). A tabela descreve apenas o caso de 12x.",
        rationale="Regra específica prevalece sobre a geral; aplicar R$ 100 a todos os "
        "parcelamentos tornaria a seção 3.1 sem efeito.",
    ),
    PolicyResolution(
        topic="Parcelamento em até 3x",
        sections="3.1",
        conflict="'sem valor mínimo de parcela (exceto abaixo de R$ 50,00)' é autocontraditório.",
        decision="Em 2x ou 3x cada parcela deve ser de no mínimo R$ 50,00. 1x é sempre permitido.",
        rationale="Interpretação que dá sentido à exceção e mantém a progressão das faixas "
        "(50 → 80 → 100).",
    ),
    PolicyResolution(
        topic="Frete grátis na região metropolitana",
        sections="5.1",
        conflict="Grátis 'acima de R$ 500,00' e taxa de R$ 35 'abaixo de R$ 500,00': o valor "
        "exato de R$ 500,00 não é coberto.",
        decision="Pedidos de R$ 500,00 ou mais têm frete grátis.",
        rationale="Interpretação mais favorável ao consumidor (art. 47 do CDC).",
    ),
    PolicyResolution(
        topic="Região metropolitana de Campo Grande",
        sections="5.1",
        conflict="O manual dá regras de frete para a 'região metropolitana', mas não lista os "
        "municípios que a compõem.",
        decision="Entrega por motoboy (regra de R$ 500/R$ 35) só para Campo Grande. Demais "
        "cidades: Correios/Jadlog, com valor calculado no checkout.",
        rationale="Os clientes da base estão em Campo Grande ou em cidades a mais de 200 km "
        "(Dourados, Três Lagoas, Corumbá, Ponta Porã). Prometer motoboy para outro município "
        "sem confirmação seria arriscado.",
    ),
    PolicyResolution(
        topic="Data de recebimento do pedido",
        sections="4.1 e 8.1",
        conflict="Os prazos de arrependimento e de garantia contam do recebimento, mas a base "
        "só tem a previsão de entrega, não a data real.",
        decision="Usa a data informada pelo cliente; na falta dela, a previsão de entrega. A "
        "resposta deixa claro qual data foi usada.",
        rationale="É a melhor aproximação disponível e é transparente com o cliente.",
    ),
    PolicyResolution(
        topic="Troca por defeito vs. garantia legal",
        sections="4.2 e 8.1",
        conflict="4.2: troca por defeito em até 30 dias após a compra, depois 'acionar o "
        "fabricante'. 8.1: garantia legal de 90 dias a partir do recebimento.",
        decision="São regras complementares: até 30 dias da compra → troca direta na loja; até "
        "90 dias do recebimento → garantia legal (a loja intermedia); depois → garantia do "
        "fabricante. Casos de defeito são sempre encaminhados a um atendente humano.",
        rationale="Pelo CDC a loja responde solidariamente durante a garantia legal; o agente não "
        "deve negar atendimento entre o 31º e o 90º dia.",
    ),
    PolicyResolution(
        topic="Direito de arrependimento: canal da compra",
        sections="4.1",
        conflict="O arrependimento vale para compras online, mas os pedidos não informam o canal "
        "de venda.",
        decision="Todos os pedidos da base são tratados como compras online (possuem fluxo de "
        "envio/entrega).",
        rationale="A base só registra pedidos com entrega; compras no balcão não aparecem nela.",
    ),
    PolicyResolution(
        topic="Tamanho do catálogo",
        sections="1",
        conflict="O manual fala em 'mais de 300 instrumentos', incluindo sopros e cordas "
        "orquestrais; a base de produtos tem 65 itens e nenhum nessas categorias.",
        decision="O agente responde apenas com base no catálogo do sistema e, para categorias "
        "sem produtos, informa que não há itens disponíveis no momento e oferece contato humano.",
        rationale="Seção 7.1: nunca informar preço ou estoque sem consultar o sistema.",
    ),
)


def resolutions_as_dicts() -> list[dict[str, str]]:
    return [asdict(r) for r in RESOLUTIONS]
