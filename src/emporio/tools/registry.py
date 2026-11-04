"""Expõe as ferramentas como `StructuredTool` do LangChain, prontas para o agente.

As funções em `products`, `orders`, `commerce` e `store` são Python puro e testáveis sem
LLM. Aqui só as embrulhamos: o resultado vira JSON e erros viram mensagens para o modelo
(em vez de derrubar a conversa).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel

from emporio.tools import commerce, handoff, orders, policies, products, store
from emporio.tools.context import ToolContext

ToolFn = Callable[[ToolContext, Any], BaseModel]

# (nome, função, esquema de entrada, descrição para o LLM)
_SPECS: tuple[tuple[str, ToolFn, type[BaseModel], str], ...] = (
    (
        "search_products",
        products.search_products,
        products.SearchProductsInput,
        "Busca instrumentos no catálogo por categoria, faixa de preço, marca, tipo de corda, "
        "eletrônica ou texto livre. Use para perguntas abertas: 'quais violões até R$ 1000?', "
        "'tem ukulele tenor?'. Por padrão retorna só itens disponíveis para venda.",
    ),
    (
        "get_product_details",
        products.get_product_details,
        products.GetProductInput,
        "Consulta preço, disponibilidade e especificações de um produto citado pelo nome ou "
        "modelo ('quanto custa o Takamine GD20?'). Se o produto não estiver à venda, retorna "
        "alternativas. Se o nome for ambíguo, retorna candidatos para você perguntar ao cliente.",
    ),
    (
        "list_categories",
        products.list_categories,
        products.NoInput,
        "Lista as categorias de instrumentos da loja e quantos produtos há disponíveis em cada uma.",
    ),
    (
        "list_promotions",
        products.list_promotions,
        products.NoInput,
        "Lista as promoções vigentes, com preço original, desconto e preço promocional.",
    ),
    (
        "get_order_status",
        orders.get_order_status,
        orders.OrderCredentials,
        "Consulta status, itens, pagamento e rastreio de um pedido. Exige o número do pedido e o "
        "e-mail OU telefone do titular. Peça esses dados ao cliente antes de chamar; nunca os invente.",
    ),
    (
        "check_return_eligibility",
        orders.check_return_eligibility,
        orders.ReturnEligibilityInput,
        "Verifica se um pedido pode ser devolvido (arrependimento), trocado por preferência ou "
        "trocado/reparado por defeito, aplicando os prazos do manual. Exige número do pedido e "
        "e-mail ou telefone do titular.",
    ),
    (
        "payment_options",
        commerce.payment_options,
        commerce.PaymentOptionsInput,
        "Calcula formas de pagamento: preço no PIX, parcelamento sem juros permitido e combinação "
        "de pagamentos. Prefira passar product_ids (considera promoções). Nunca calcule parcelas por conta própria.",
    ),
    (
        "shipping_quote",
        commerce.shipping_quote,
        commerce.ShippingQuoteInput,
        "Informa se a loja entrega numa cidade, por qual transportadora, o prazo e o valor quando a "
        "entrega é em Campo Grande. Só a cidade é obrigatória: para 'vocês entregam em X?', chame já, "
        "sem perguntar o produto antes. Passe product_ids quando souber (frete especial para itens grandes).",
    ),
    (
        "search_policies",
        policies.search_policies,
        policies.SearchPoliciesInput,
        "Consulta o manual de políticas da loja: trocas e devoluções, garantia, formas de pagamento, "
        "frete, promoções, privacidade (LGPD), endereço e contatos. Use para qualquer pergunta sobre "
        "regras. Para casos de um pedido específico prefira check_return_eligibility, que calcula os prazos.",
    ),
    (
        "escalate_to_human",
        handoff.escalate_to_human,
        handoff.EscalateInput,
        "Registra o caso para a equipe humana e devolve um protocolo. Use para reclamações, defeitos, "
        "cancelamentos, devoluções aprovadas (requires_human), quando o cliente pedir uma pessoa ou "
        "quando você não souber responder. Exige um telefone ou e-mail de contato do cliente.",
    ),
    (
        "store_status",
        store.store_status,
        products.NoInput,
        "Informa se a loja está aberta agora, o horário de hoje, quando abre novamente, o endereço e "
        "os contatos. Use para perguntas sobre horário, localização ou quando o cliente quiser falar "
        "com a equipe.",
    ),
)


def _wrap(ctx: ToolContext, name: str, fn: ToolFn, schema: type[BaseModel], description: str) -> BaseTool:
    def run(**kwargs: Any) -> str:
        try:
            result = fn(ctx, schema(**kwargs))
        except Exception as exc:  # noqa: BLE001
            # O LangChain só converte ToolException em mensagem; qualquer outro erro
            # derrubaria a conversa em vez de deixar o modelo se corrigir.
            raise ToolException(str(exc)) from exc
        return result.model_dump_json(exclude_none=True)

    return StructuredTool.from_function(
        func=run,
        name=name,
        description=description,
        args_schema=schema,
        handle_tool_error=lambda e: f"Erro ao executar {name}: {e}",
        handle_validation_error=lambda e: f"Parâmetros inválidos para {name}: {e}",
    )


def build_tools(ctx: ToolContext) -> list[BaseTool]:
    return [_wrap(ctx, *spec) for spec in _SPECS]


TOOL_NAMES = tuple(spec[0] for spec in _SPECS)
