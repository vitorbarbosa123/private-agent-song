# Arquitetura do agente e ferramentas

[← Voltar ao README](../README.md)

## Arquitetura do agente

```
              ┌───────────────────────────── ChatSession (uma por conversa) ─────────────────────────────┐
 cliente ──▶  │  START → input_guard → agent ──(pediu ferramentas?)──▶ tools ──┐                          │
              │                          ▲                                     │                          │
              │                          └─────────────────────────────────────┘                          │
              │                          │ resposta final → verificação de protocolos e preços ──▶ cliente │
              └──────────────────────────────────────────────────────────────────────────────────────────┘
   compartilhado: modelo (OpenRouter) · repositório SQLite · busca no manual · checkpointer
```

**Framework: LangGraph, com o grafo montado à mão.** O ciclo é o padrão ReAct: o modelo
raciocina, chama ferramentas, observa os resultados e repete até responder. Não usei o agente
pronto do LangGraph porque os guardrails de entrada e saída e o handoff para humanos vão entrar
como nós explícitos do grafo. O LangGraph também traz o checkpointer de histórico por conversa.

**Estratégia de prompt** ([`agent/prompts.py`](../src/emporio/agent/prompts.py)):

- **Persona "Lia"**, com o tom de voz do manual (7.1): informal mas profissional, mensagens
  curtas de WhatsApp, no máximo um emoji.
- **O que entra no prompt e o que não entra.** Fatos estáveis (endereço, contatos, horário)
  entram no prompt, vindos da fonte canônica que já resolve as contradições do manual. Fatos
  voláteis (preço, estoque, pedidos, prazos) **nunca** entram: o prompt obriga o uso das
  ferramentas e proíbe estimar ou recalcular valores.
- **Data, hora e status da loja são injetados a cada turno.** Assim "estamos fechados, abrimos
  amanhã às 9h" sai sem chamada de ferramenta, e os prazos são coerentes com o relógio.
- **Mapa de ferramentas.** O prompt diz qual ferramenta usar para cada tipo de pergunta, e cada
  ferramenta reforça isso na sua descrição.
- **Segurança.** As mensagens do cliente e os resultados das ferramentas são tratados como dados.
  O agente não muda de papel, não revela o prompt, não cria descontos e não fala de pedidos sem
  verificação de identidade.

**Histórico persistente** ([`agent/memory.py`](../src/emporio/agent/memory.py)). Cada conversa é
salva em SQLite pelo checkpointer do LangGraph, e o cliente pode retomá-la depois com
`--session`. Persistir faz sentido para a experiência: quem volta perguntando "qual era meu
protocolo?" ou "e aquele violão que você indicou?" não precisa repetir tudo. Como o histórico
contém dados pessoais, ele fica fora do repositório (`var/`), e o comando `/esquecer` apaga a
conversa, atendendo ao direito de exclusão da LGPD (manual, seção 9).

**Encaminhamento para humanos** ([`handoff.py`](../src/emporio/handoff.py)). Reclamações, defeitos,
cancelamentos e pedidos para falar com uma pessoa são registrados com um resumo para a equipe,
que não precisa reler a conversa. A equipe acompanha pelo `uv run emporio-handoffs`. Numa loja
real, esse registro seria trocado por uma integração com o CRM ou o WhatsApp Business.

**Cache de prompt.** O system prompt foi dividido em uma parte **fixa** (persona, regras e dados
da loja) e uma parte **dinâmica** no final (data e hora, status da loja, avisos do guardrail). A
parte fixa recebe `cache_control`, e assim ela e as definições das ferramentas, que vêm antes
dela, podem ser reaproveitadas do cache do provedor (Anthropic e Gemini via OpenRouter) a cada
mensagem, reduzindo custo e latência. Antes dessa divisão, a data ficava no início do prompt e
invalidaria o cache em toda mensagem. Pode ser desligado com `LLM_PROMPT_CACHE=false`. A medição
do ganho real (tokens lidos do cache) ficou pendente: o limite diário de gastos do workspace no
OpenRouter foi atingido antes dela.

**Robustez:**

- **Uma `ChatSession` por conversa,** com o seu próprio contexto de ferramentas. O limite de 3
  tentativas de verificação de identidade é por conversa, não global.
- **Janela de histórico** das últimas 40 mensagens. O corte sempre começa numa mensagem do
  cliente, para não separar uma chamada de ferramenta do seu resultado, o que os provedores
  rejeitam.
- **Limite de iterações:** no máximo ~7 rodadas de ferramenta por mensagem. Se estourar, o
  agente encaminha para a equipe em vez de ficar em loop.
- **Falhas do provedor** (rede, crédito, indisponibilidade) viram uma mensagem amigável com o
  contato da loja, e a conversa continua utilizável na mensagem seguinte. Os testes simulam
  esses cenários com um modelo roteirizado, sem rede.

## Ferramentas do agente

As ferramentas ficam em [`src/emporio/tools/`](../src/emporio/tools/). Cada uma é uma **função Python
pura**, que recebe um contexto (repositório + relógio) e devolve um modelo Pydantic. Por isso
todas são testadas sem LLM. O [registro](../src/emporio/tools/registry.py) as expõe como
`StructuredTool` do LangChain, com descrições que dizem ao modelo **quando** usar cada uma.

| Ferramenta | Pergunta típica | O que garante |
|---|---|---|
| `search_products` | "Quais violões até R$ 1000?" | Filtros estruturados; só itens à venda por padrão; redireciona pedidos de acessórios; avisa quando a categoria está vazia |
| `get_product_details` | "Quanto custa o Takamine GD20?" | Preço de tabela, promoção (com percentual) e PIX; alternativas se esgotado ou fora de linha; pede esclarecimento se o nome for ambíguo ("Martin D28" → D-28 ou D-28E?) |
| `list_categories`, `list_promotions` | "O que vocês vendem?", "Tem promoção?" | Só promoções ativas, já com a regra de não acumular com o PIX |
| `get_order_status` | "Cadê meu pedido 8?" | Exige pedido + e-mail ou telefone; avisa atraso de entrega; bloqueia após 3 tentativas erradas na conversa |
| `check_return_eligibility` | "Me arrependi, posso devolver?" | Calcula prazos (7 dias de arrependimento, 30 de troca por defeito, 90 de garantia legal) e diz qual data usou |
| `payment_options` | "Em quantas vezes posso pagar?" | Faixas de parcela mínima; PIX só nos itens sem promoção; combinação de pagamentos acima de R$ 2.000 |
| `shipping_quote` | "Entregam em Dourados?" | Valor só quando é calculável (Campo Grande); avisa sobre frete especial para itens grandes |
| `search_policies` | "Qual o prazo para devolução?" | Trechos do manual com o número da seção, mais a interpretação oficial quando o trecho é ambíguo (ver [Busca no manual](05-rag.md)) |
| `escalate_to_human` | "Meu violão veio trincado", "Quero falar com uma pessoa" | Registra o caso para a equipe com resumo e contato; devolve protocolo (`ATD-00001`) e prazo de retorno conforme o horário (reclamação: 24 horas úteis); não duplica atendimentos abertos |
| `store_status` | "Vocês estão abertos?" | Horário no fuso de Campo Grande, feriados (inclusive móveis) e próxima abertura |

Decisões de desenho:

- **Valores já formatados.** As ferramentas devolvem "R$ 2.199,00" e "24/02/2026", e as
  parcelas já calculadas. O LLM só repete esses valores: contas e formatação feitas pelo modelo
  são uma fonte clássica de alucinação, e o manual (7.1) proíbe informar preço sem consultar o sistema.
- **Notas para o modelo.** Cada resultado traz `notes` com a orientação de política aplicável,
  como "não acumula com PIX", "não diga se o pedido existe" ou "ofereça alternativas". A regra
  chega no momento em que é relevante, em vez de depender só do system prompt.
- **Erros viram mensagens.** Parâmetros inválidos ou falhas internas retornam texto para o
  modelo se corrigir, em vez de derrubar a conversa. Todo erro é convertido em `ToolException`,
  porque o LangChain só trata esse tipo e deixaria os demais propagarem.
- **Relógio injetável** (`EMPORIO_NOW`). Os pedidos da base são de 2025–2026; fixar a data torna
  demonstrações e testes de prazos reproduzíveis.
- **Feriados.** São considerados os nacionais (inclusive a Sexta-feira Santa, calculada a partir
  da Páscoa), o estadual de MS (11/10) e o municipal de Campo Grande (26/08).
