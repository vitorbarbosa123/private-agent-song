# Conversas de exemplo

Conversas reais com a assistente, geradas por `uv run emporio-export-examples` a partir do roteiro em [`evals/example_conversations.yaml`](../evals/example_conversations.yaml). Em cada resposta, o bloco "Ferramentas chamadas" mostra o que a assistente consultou.

| # | Conversa | O que mostra |
|---|---|---|
| 01 | [Catálogo, indicação e parcelamento](01-catalogo-e-indicacao.md) | Busca no catálogo com filtro de preço (só itens à venda), indicação para iniciante com base nos dados, e parcelamento calculado pela política (faixas de parcela mínima). |
| 02 | [Preço, desconto no PIX e entrega fora de Campo Grande](02-preco-pix-e-frete.md) | Consulta de preço (ignorando uma promoção inativa), economia no PIX vinda da ferramenta e regras de frete para outra cidade, sem inventar valor. |
| 03 | [Devolução por arrependimento (dentro do prazo)](03-devolucao-por-arrependimento.md) | Situação não trivial: verificação de identidade antes de consultar o pedido, cálculo do prazo de 7 dias pela política (a partir da previsão de entrega) e encaminhamento para a equipe com protocolo, só depois da concordância da cliente. |
| 04 | [Defeito depois de 30 dias (garantia legal) e encaminhamento](04-defeito-e-garantia.md) | Situação não trivial: fora dos 30 dias de troca direta, mas dentro da garantia legal de 90 dias. A assistente aplica a interpretação documentada para o conflito entre as seções 4.2 e 8.1 do manual e registra o caso para a equipe. |
| 05 | [Loja fechada, fora do escopo, manipulação e dados de cartão](05-limites-e-seguranca.md) | Horário no domingo com a próxima abertura, recusa de acessórios, resistência a tentativa de manipulação e proteção de dados de cartão (o número é removido antes de chegar ao modelo e ao histórico). |
