# Empório da Música — Agente de Atendimento

Protótipo de um agente de atendimento por mensagens de texto para a **Empório da Música**, loja
fictícia de instrumentos musicais em Campo Grande/MS. Desenvolvido como desafio técnico para a
vaga de AI Engineer na Artefact.

> **Status:** em desenvolvimento. Concluídos: **tratamento dos dados**, **camada de acesso aos
> dados**, **configuração do modelo**, **ferramentas do agente**, **busca no manual (RAG)**,
> **agente com interface de terminal** e **histórico persistente com encaminhamento para humanos**. As seções sobre o agente serão preenchidas conforme a
> implementação avançar.

## Sumário

- [Como rodar](#como-rodar)
- [Conversando com o agente](#conversando-com-o-agente)
- [Modelo de linguagem: como trocar](#modelo-de-linguagem-como-trocar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Tratamento dos dados](#tratamento-dos-dados)
- [Interpretações do manual de políticas](#interpretações-do-manual-de-políticas)
- [Camada de acesso aos dados](#camada-de-acesso-aos-dados)
- [Ferramentas do agente](#ferramentas-do-agente)
- [Busca no manual de políticas (RAG)](#busca-no-manual-de-políticas-rag)
- [Arquitetura do agente](#arquitetura-do-agente)
- [Limitações conhecidas](#limitações-conhecidas)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)

## Como rodar

Pré-requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # cria o ambiente virtual e instala as dependências
cp .env.example .env       # e preencha LLM_API_KEY (chave do OpenRouter)
uv run emporio-clean-data  # trata os dados brutos e grava os artefatos em data/processed/
uv run emporio-llm-check   # confere a configuração e faz uma chamada mínima ao modelo
uv run emporio-eval-retrieval [--dataset holdout]  # avalia a busca no manual de políticas
uv run emporio-chat        # conversa com a assistente no terminal
uv run emporio-handoffs    # painel da equipe: atendimentos encaminhados pela assistente
uv run pytest              # roda os testes (não fazem chamadas ao modelo)
```

## Conversando com o agente

```bash
uv run emporio-chat                          # conversa interativa
uv run emporio-chat --debug                  # mostra as ferramentas chamadas e seus resultados
uv run emporio-chat --now 2026-03-02T10:30   # simula data/hora (os pedidos da base são de 2025-2026)
uv run emporio-chat --model openai/gpt-4o-mini            # testa outro modelo sem editar o .env
uv run emporio-chat -m "Oi" -m "Quanto custa o Takamine GD20?"  # roteiro não interativo
uv run emporio-chat --sessions               # lista conversas salvas
uv run emporio-chat --session <id>           # retoma uma conversa (o id aparece ao sair)
uv run emporio-chat --no-persist             # não grava histórico nem atendimentos
uv run emporio-handoffs [--all] [--close N]  # equipe: lista e encerra atendimentos encaminhados
```

Durante a conversa: `/novo` inicia outra conversa, `/esquecer` apaga o histórico da conversa
atual, `/debug` liga e desliga os detalhes, `/sair` encerra.

Dados de teste para consultar pedidos (fictícios, de `data/`): pedido **8** com o e-mail
`anacarol.ferreira@coldmail.com` (enviado, com rastreio) ou pedido **7** com
`leticia.rocha@jmail.com` (entregue). Com `--now 2026-02-20T10:00`, o pedido 7 ainda está
dentro do prazo de arrependimento.

## Modelo de linguagem: como trocar

O projeto acessa o modelo pelo **[OpenRouter](https://openrouter.ai)**, com uma única chave de API.
O modelo padrão é um **preset** da plataforma (`@preset/emporio-agent`): modelo principal,
fallbacks e parâmetros ficam configurados no painel do OpenRouter, sem mudança de código.

**Para testar outro modelo, basta alterar uma variável no `.env`:**

```bash
LLM_MODEL=openai/gpt-4o-mini            # qualquer ID de https://openrouter.ai/models
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_MODEL=@preset/emporio-agent         # volta ao preset padrão
```

| Variável | Para quê | Padrão |
|---|---|---|
| `LLM_API_KEY` (ou `OPENROUTER_API_KEY`) | Chave de API | — |
| `LLM_MODEL` | Modelo do agente | `@preset/emporio-agent` |
| `LLM_FAST_MODEL` | Modelo barato para tarefas auxiliares (guardrails, avaliação) | usa `LLM_MODEL` |
| `LLM_FALLBACK_MODELS` | Fallbacks na própria requisição, separados por vírgula (só OpenRouter) | nenhum |
| `LLM_BASE_URL` | Qualquer API compatível com a da OpenAI: OpenAI direto, Ollama local etc. | OpenRouter |
| `LLM_MAX_TOKENS` | Limite de tokens da resposta. Sem ele, o OpenRouter reserva crédito para o máximo do modelo e pode recusar a chamada em chaves com limite de gasto | `1024` |
| `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Ajustes finos | `0.2`, `60`, `2` |
| `EMBEDDING_MODEL` | Modelo de embeddings da busca no manual (mesma chave e endpoint). Vazio = só BM25, sem rede | `google/gemini-embedding-001` |
| `RETRIEVAL_MODE` | `embeddings`, `hybrid` ou `bm25` | `embeddings` |
| `EMPORIO_STATE_DIR` | Onde ficam o histórico das conversas e os atendimentos encaminhados (SQLite) | `var/` |
| `EMPORIO_NOW` | Fixa a data e hora vistas pelo agente (ex.: `2026-03-02T10:30`), para demonstrações reproduzíveis | relógio real |

Exemplo com modelo local, sem chave: `LLM_BASE_URL=http://localhost:11434/v1` e
`LLM_MODEL=llama3.1`. O comando `uv run emporio-llm-check` mostra a configuração ativa (com a
chave mascarada) e testa uma chamada simples e outra **com ferramentas**, de que o agente depende.
Para cada uma, informa qual modelo de fato atendeu, o que é útil para confirmar um fallback. Em
caso de erro, dá dicas para os problemas mais comuns do OpenRouter: crédito, chave inválida ou
guardrails de privacidade do workspace que excluem os endpoints do modelo.

**Por que OpenRouter.** Uma única chave e uma API compatível com a da OpenAI dão acesso a modelos
de vários fornecedores. Isso permite trocar ou comparar modelos sem mexer em código e configurar
fallbacks automáticos se um provedor cair. Como o cliente (`langchain-openai`) fala o protocolo
da OpenAI, o mesmo código funciona com outros provedores compatíveis. Toda a configuração está em
[`src/emporio/config.py`](src/emporio/config.py) e a criação do cliente em
[`src/emporio/llm.py`](src/emporio/llm.py).

## Estrutura do projeto

```
data/
├── *.csv, políticas_da_loja.pdf     # dados brutos fornecidos pela loja (nunca alterados)
└── processed/                       # artefatos gerados pelo pipeline (não versionados,
                                     # exceto o relatório de qualidade)
src/emporio/
├── config.py · llm.py               # configuração (.env) e fábrica do modelo (OpenRouter)
├── agent/                           # grafo LangGraph, prompt, memória e verificação de respostas
├── handoff.py                       # registro de atendimentos encaminhados + painel da equipe
├── cli.py                           # interface de terminal (emporio-chat)
├── policy_rules.py                  # regras de negócio canônicas + conflitos resolvidos do manual
├── business_hours.py                # relógio da loja, horário de funcionamento e feriados
├── repository/                      # consultas fixas, somente leitura, sobre o SQLite tratado
├── tools/                           # ferramentas do agente (funções puras + registro LangChain)
├── rag/                             # busca no manual: BM25, embeddings, avaliação
└── data/
    ├── pipeline.py                  # orquestração, escrita dos artefatos e relatório
    ├── products.py                  # catálogo: specs, descrições, disponibilidade
    ├── promotions.py                # promoções ativas e preço vigente
    ├── categories.py · customers.py · orders.py
    ├── policies.py                  # extração do PDF e divisão em seções
    └── issues.py · utils.py · paths.py
evals/                               # perguntas de avaliação da busca (dev e holdout)
tests/
```

## Tratamento dos dados

### Princípio: sinalizar em vez de corrigir silenciosamente

Os dados brutos têm inconsistências propositais. Um agente de atendimento que repassa dado errado
ao cliente pode configurar propaganda enganosa (o próprio manual alerta para isso na seção 7.1).
Por isso o pipeline segue três regras:

1. **Os arquivos originais nunca são alterados.** Toda saída vai para `data/processed/`.
2. **Só corrigimos o que é inequívoco**, como um erro de digitação. Nos demais casos o valor
   original é mantido, e o problema é exposto em **colunas derivadas e flags** que o agente vai
   consultar.
3. **Toda decisão é auditável.** Cada problema encontrado é registrado com tabela, registro, regra,
   severidade e ação tomada, e todos são reunidos em
   [`data/processed/data_quality_report.md`](data/processed/data_quality_report.md).

Os CSVs são lidos como texto puro (`dtype=str`) e cada conversão de tipo é feita e validada
explicitamente. Valores inválidos são anulados e registrados, em vez de quebrarem o pipeline ou
serem convertidos silenciosamente pelo pandas.

### Decisões por tabela

| Tabela | Problema encontrado | Decisão | Por quê |
|---|---|---|---|
| **products** | Em 7 produtos (IDs 135–144), a descrição cita outro fabricante (ex.: "Music Man Bass" descrito como "Fender Jazz Bass") ou contradiz as specs (5 cordas vs. 4; 88 teclas vs. 61) | Conflito detectado automaticamente por marca, modelo característico ("Precision" indica Fender) e números. A descrição original fica em `description_original`, a coluna `description` passa a ser gerada a partir das specs e `description_verified=False` | Não sabemos qual campo está certo. O nome é o que o cliente pergunta ("quanto custa o Yamaha Bass?") e as specs são estruturadas, então são as fontes mais confiáveis. Uma descrição genérica e correta é melhor que uma rica e errada |
| | O campo `specs.strings` tem dois significados: tipo de corda (`"nylon"`, `"steel"`) em violões e ukuleles, quantidade (`"4"`, `"6"`) em guitarras e baixos | Separado em `string_type` (nylon/aço) e `string_count` (inteiro). Os demais campos numéricos e booleanos também são convertidos | Permite filtros corretos, como "violões de nylon" ou "baixos de 5 cordas" |
| | Status e estoque incoerentes: descontinuado com 13 unidades (136), `coming_soon` com estoque (130), ativo esgotado (96) | Nova coluna `availability` (`in_stock`, `out_of_stock`, `discontinued`, `coming_soon`) e `is_sellable`, que só é verdadeiro para produtos ativos com estoque | O manual (7.3) manda tratar descontinuados como fora do catálogo e nunca confirmar disponibilidade sem checar estoque |
| | "Giannini GN-15 Nylon **Cedr** Natural" (84) | Corrigido para "Cedro", por meio de um dicionário explícito que só é aplicado se o nome original bater exatamente | Correção inequívoca |
| **promotions** | 25 promoções, só 4 ativas, sem datas de vigência. Alguns produtos aparecem em várias promoções | Vale apenas `is_active = 1`. Se houver mais de uma ativa, vale a de maior desconto. O preço vigente é calculado no pipeline (`promotion_price_brl`, `pix_price_brl`) | Manual 6.2: promoções não são cumulativas e o PIX (5%) não vale sobre preço promocional. Manual 7.3: nunca prometer desconto não vigente. Ex.: o Takamine GD20 tem uma promoção de 12% **inativa** |
| **orders** | O total registrado difere da soma dos itens nos pedidos 3 (R$ 48 a menos) e 20 (R$ 88 a menos) | O total registrado é **mantido**. A diferença fica em `total_divergence_brl` | Pedido é registro histórico: o valor cobrado pode incluir descontos ou preços antigos. O agente informa o que foi cobrado |
| | Parcelamentos que violam a política: pedidos 9 e 16 (6x abaixo de R$ 80) e 18 (12x de R$ 38) | `payment_method` é decomposto em `payment_type` + `installments`; a coluna `installment_plan_valid=False` marca os casos | O agente não deve usar esses pedidos como precedente de condição de pagamento |
| | O produto 130 está `coming_soon`, mas já foi vendido e entregue (pedido 3) | Sinalizado como status de cadastro desatualizado | Sem base para escolher qual informação está certa |
| | Coerência entre status e rastreio, formato do código (BR + 9 + BR) e datas | Validados. Os dados atuais não violam nenhuma dessas regras | — |
| **customers** | Os clientes 11 e 43 compartilham o mesmo e-mail. Há nomes possivelmente duplicados ("Diego Fernandes Castro" / "Diego Castro") | Nenhuma fusão automática. Telefone e e-mail são normalizados (`phone_digits`, `email_normalized`) | LGPD: e-mail sozinho não identifica o cliente. O agente vai exigir **número do pedido + e-mail ou telefone** antes de revelar dados de um pedido |
| **categories** | Sopros (madeiras e metais) e cordas orquestrais não têm nenhum produto, embora o manual diga que a loja trabalha com eles | Contagem de produtos por categoria e sinalização | O agente deve dizer que não há itens disponíveis no momento, e não inventar produtos |
| **manual (PDF)** | A extração padrão do pypdf quebra cada palavra em uma linha (o PDF foi gerado pelo Google Docs). Há cabeçalhos e rodapés repetidos e caracteres invisíveis (U+200B) | Extração em modo `layout`, limpeza, e divisão nas 29 seções numeradas do manual. Listas numeradas internas (ex.: "1. Saudação") não são confundidas com títulos | Seções coesas são a unidade natural de recuperação (RAG) e permitem que o agente cite a seção usada |

### Artefatos gerados (`data/processed/`)

| Arquivo | Conteúdo |
|---|---|
| `*.csv` e `emporio.db` | Tabelas tratadas, em CSV e em SQLite (para as ferramentas de consulta do agente) |
| `policies.md` / `policy_sections.json` | Manual em Markdown e dividido em seções (insumo do RAG) |
| `store_facts.json` | Dados institucionais canônicos e os conflitos do manual resolvidos |
| `data_quality_issues.csv` / `data_quality_report.md` | Todos os problemas encontrados e a ação tomada |

## Interpretações do manual de políticas

O manual tem trechos contraditórios. As regras computáveis (parcelamento, frete, prazos) e a
interpretação adotada para cada conflito ficam centralizadas em
[`src/emporio/policy_rules.py`](src/emporio/policy_rules.py). Esse módulo é usado tanto pelo
pipeline, para validar pedidos, quanto pelo agente.

| Conflito | Decisão | Motivo |
|---|---|---|
| Telefone: (67) 3341-4444 (capa e 1.2) vs. WhatsApp (67) 3321-4500 (seção 7) | (67) 3341-4444 | Aparece duas vezes, inclusive na tabela de dados cadastrais |
| E-mail com e sem acento (`empóriodamusica`) | Sem acento | O acento no domínio é quase certamente um erro de autocorreção |
| Tabela da seção 3 ("parcela mínima R$ 100") vs. faixas da 3.1 | Valem as faixas da 3.1 | A regra específica prevalece sobre a geral |
| "Até 3x sem valor mínimo (exceto abaixo de R$ 50)" | 2x e 3x exigem parcela de no mínimo R$ 50; 1x é sempre permitido | É a única leitura que dá sentido à exceção e mantém a progressão 50 → 80 → 100 |
| Frete grátis "acima" e taxa "abaixo" de R$ 500: o valor exato fica sem regra | R$ 500,00 ou mais tem frete grátis | Interpretação mais favorável ao consumidor (CDC, art. 47) |
| Troca por defeito em 30 dias (4.2) vs. garantia legal de 90 dias (8.1) | Regras complementares: loja troca até 30 dias; garantia legal até 90 dias, com intermediação da loja; depois, fabricante. Casos de defeito são encaminhados a um humano | A loja responde solidariamente durante a garantia legal |
| A "região metropolitana" do frete por motoboy não tem municípios definidos | Motoboy (R$ 35 ou grátis a partir de R$ 500) só em Campo Grande; outras cidades, Correios/Jadlog com valor no checkout | As outras cidades da base ficam a mais de 200 km; prometer motoboy seria arriscado |
| Os prazos de arrependimento e de garantia contam do recebimento, mas a base não registra a data real de entrega | Usa a data informada pelo cliente; na falta dela, a previsão de entrega, e a resposta diz qual data foi usada | É a melhor aproximação disponível, e é transparente |
| O direito de arrependimento vale para compras online, mas os pedidos não informam o canal | Todos os pedidos da base são tratados como online | Todos passam por fluxo de envio e entrega |
| "Mais de 300 instrumentos" vs. 65 produtos na base | O agente responde só com o que está no sistema | Manual 7.1: nunca informar sem consultar o sistema |

## Camada de acesso aos dados

As ferramentas do agente vão consultar os dados por meio de
[`StoreRepository`](src/emporio/repository/repository.py), que retorna modelos Pydantic
tipados.

| Decisão | Motivo |
|---|---|
| **Consultas fixas e parametrizadas, em vez de text-to-SQL.** O LLM escolhe a ferramenta e os filtros (categoria, faixa de preço, marca, tipo de corda, com eletrônica…), e o código monta a consulta com trechos fixos e parâmetros vinculados | Elimina SQL injection e consultas alucinadas, e protege dados de clientes. O custo é perder flexibilidade em perguntas analíticas, que fogem do escopo de um atendimento |
| **Conexão somente leitura** (`mode=ro`) | O agente nunca altera dados |
| **Busca textual tolerante**: normalização sem acentos, cobertura de palavras, plurais ("violão"/"violões"), hífens ("d28"/"D-28") e erros de digitação ("yamha") | Clientes não escrevem o nome exato do produto. Regras simples e testadas bastam para 65 produtos; embeddings seriam desproporcionais aqui |
| **Busca por nome inclui produtos esgotados e fora de linha** | Para responder "está esgotado, mas temos estas alternativas" (manual 7.3), em vez de "não encontrei" |
| **Filtro de preço usa o preço vigente** (promocional, se houver) | "Até R$ 2.000" deve incluir o Crafter HT-100, que custa R$ 2.399 de tabela e R$ 1.967,18 em promoção |
| **Pedido só é exibido com número + e-mail ou telefone do titular.** Todos os dados informados precisam conferir, a comparação é em tempo constante, e a resposta é idêntica para "pedido inexistente" e "dados não conferem" | LGPD: não revela quais pedidos existem nem dados de terceiros. O modelo `Order` não carrega e-mail nem telefone |
| **Banco gerado sob demanda** (`open_repository` roda o pipeline se o SQLite não existir) | Quem clona o repositório não precisa de um passo manual extra |

## Ferramentas do agente

As ferramentas ficam em [`src/emporio/tools/`](src/emporio/tools/). Cada uma é uma **função Python
pura**, que recebe um contexto (repositório + relógio) e devolve um modelo Pydantic. Por isso
todas são testadas sem LLM. O [registro](src/emporio/tools/registry.py) as expõe como
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
| `search_policies` | "Qual o prazo para devolução?" | Trechos do manual com o número da seção, mais a interpretação oficial quando o trecho é ambíguo (ver abaixo) |
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

## Busca no manual de políticas (RAG)

Implementada em [`src/emporio/rag/`](src/emporio/rag/) e exposta ao agente pela ferramenta
`search_policies`.

**Chunking.** Cada seção numerada do manual vira um chunk, e o título da seção-mãe é incorporado
("Política de Frete e Entregas › 5.1. Entregas na Região Metropolitana…"). As seções têm no máximo
~800 caracteres e tratam de um único assunto, então o corte natural do documento é melhor que
janelas de tamanho fixo. Isso também permite citar a seção na resposta. São 26 chunks; seções que
têm só título são omitidas.

**Interpretações oficiais junto dos trechos.** Quando a seção mais relevante tem uma contradição
resolvida em `policy_rules.RESOLUTIONS`, a ferramenta devolve a decisão junto com o texto. Exemplo:
a seção 7 cita o WhatsApp (67) 3321-4500, e a resposta acrescenta "número canônico:
(67) 3341-4444". Assim o modelo não repete uma contradição do manual.

**Avaliação e escolha da estratégia.** Montei dois conjuntos de perguntas de clientes, cada uma com
as seções esperadas:

- [`evals/policy_retrieval.json`](evals/policy_retrieval.json) (**dev**, 28 perguntas): usado
  para ajustar a busca.
- [`evals/policy_retrieval_holdout.json`](evals/policy_retrieval_holdout.json) (**holdout**, 22
  paráfrases novas): escrito antes de qualquer medição nele e nunca usado para ajustes.

Comparação de modelos de embedding (dev, busca só por embeddings):

| Modelo | hit@1 | hit@3 | MRR |
|---|---:|---:|---:|
| `openai/text-embedding-3-small` | 75% | 96% | 0,85 |
| `openai/text-embedding-3-large` | 71% | 93% | 0,82 |
| `qwen/qwen3-embedding-8b` | 61% | 93% | 0,77 |
| **`google/gemini-embedding-001`** | **82%** | **96%** | **0,89** |

Comparação de estratégias com `gemini-embedding-001`:

| Modo | dev hit@1 | dev hit@3 | **holdout hit@1** | **holdout hit@3** | holdout MRR |
|---|---:|---:|---:|---:|---:|
| BM25 (+ stemming e sinônimos) | 86% | 100% | 73% | 82% | 0,77 |
| **Embeddings** | 82% | 96% | **95%** | **100%** | **0,98** |
| Híbrido (Reciprocal Rank Fusion) | 86% | 100% | 86% | 91% | 0,89 |

**O que os números mostraram.** O BM25 parecia o melhor no dev, mas eu tinha ajustado os
sinônimos dele olhando os erros desse mesmo conjunto. No holdout ele cai para 82% de hit@3: não
generaliza para paráfrases novas ("até que horas ficam abertos?", "o captador parou de
funcionar"). A minha hipótese inicial, de que o híbrido seria o melhor, também não se confirmou:
com pesos iguais no RRF, o BM25 puxa o resultado para baixo. Por isso:

- o **padrão é busca só por embeddings** (`RETRIEVAL_MODE=embeddings`);
- o **BM25 é o fallback automático**: se a API de embeddings falhar, a busca degrada em vez de
  falhar, e o agente é avisado;
- o modo híbrido continua disponível por configuração, mas não calibrei os pesos do RRF no
  holdout, para não contaminá-lo.

**Custo e latência.** Os vetores das 26 seções são calculados uma vez e guardados em cache
(`data/processed/policy_embeddings.json`, indexado por modelo + hash do texto). Cada pergunta do
cliente gera uma chamada de embedding, de custo desprezível (~US$ 0,000001).

## Arquitetura do agente

```
              ┌──────────────────────── ChatSession (uma por conversa) ────────────────────────┐
 cliente ──▶  │  START → agent ──(pediu ferramentas?)──▶ tools ──┐                              │
              │            ▲                                     │                              │
              │            └─────────────────────────────────────┘     resposta ──▶ cliente     │
              └─────────────────────────────────────────────────────────────────────────────────┘
   compartilhado: modelo (OpenRouter) · repositório SQLite · busca no manual · checkpointer
```

**Framework: LangGraph, com o grafo montado à mão.** O ciclo é o padrão ReAct: o modelo
raciocina, chama ferramentas, observa os resultados e repete até responder. Não usei o agente
pronto do LangGraph porque os guardrails de entrada e saída e o handoff para humanos vão entrar
como nós explícitos do grafo. O LangGraph também traz o checkpointer de histórico por conversa.

**Estratégia de prompt** ([`agent/prompts.py`](src/emporio/agent/prompts.py)):

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

**Histórico persistente** ([`agent/memory.py`](src/emporio/agent/memory.py)). Cada conversa é
salva em SQLite pelo checkpointer do LangGraph, e o cliente pode retomá-la depois com
`--session`. Persistir faz sentido para a experiência: quem volta perguntando "qual era meu
protocolo?" ou "e aquele violão que você indicou?" não precisa repetir tudo. Como o histórico
contém dados pessoais, ele fica fora do repositório (`var/`), e o comando `/esquecer` apaga a
conversa, atendendo ao direito de exclusão da LGPD (manual, seção 9).

**Encaminhamento para humanos** ([`handoff.py`](src/emporio/handoff.py)). Reclamações, defeitos,
cancelamentos e pedidos para falar com uma pessoa são registrados com um resumo para a equipe,
que não precisa reler a conversa. A equipe acompanha pelo `uv run emporio-handoffs`. Numa loja
real, esse registro seria trocado por uma integração com o CRM ou o WhatsApp Business.

**Verificação das respostas** ([`agent/verification.py`](src/emporio/agent/verification.py)).
Num teste real, o modelo disse "vou registrar seu caso", **não** chamou a ferramenta e inventou
um protocolo ("#ESCALATE-7-DEFEITO-LETICIA"). Ajustar o prompt reduz esse risco, mas não o
elimina. Por isso cada resposta final é conferida de forma determinística: todo protocolo citado
precisa ter sido emitido por `escalate_to_human` na conversa. Se não foi, o modelo recebe uma
correção (que não fica no histórico) e responde de novo. Se insistir, o cliente recebe uma
mensagem segura com o WhatsApp da loja.

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

## Limitações conhecidas

- **Limite de tentativas de verificação por processo.** O contador de tentativas erradas de
  identificação é por conversa, mas fica em memória: se a conversa for retomada em outro
  processo, ele recomeça. Numa API real, ficaria no estado persistido da conversa.

- **Validação de marcas por dicionário.** A detecção de descrições conflitantes usa uma lista de
  marcas e modelos conhecidos. Uma marca nova no catálogo precisa ser adicionada a `BRANDS` em
  `products.py`.
- **Busca textual por regras.** Sinônimos ("acústico" vs. "folk", "elétrico" vs.
  "eletroacústico") não são tratados. Com um catálogo maior, valeria uma busca híbrida (BM25 +
  embeddings).
- **Data real de entrega.** A base só tem a previsão de entrega; os prazos de devolução usam a
  data informada pelo cliente ou essa previsão.
- **Feriados municipais de outras cidades e pontos facultativos** (Carnaval, Corpus Christi) não
  são considerados no horário da loja.
- **Conjuntos de avaliação pequenos** (28 + 22 perguntas, escritas por mim). Servem para comparar
  estratégias e pegar regressões, mas as diferenças de poucos pontos percentuais não são
  estatisticamente robustas. Com mais tempo, coletaria perguntas reais do WhatsApp da loja.
- **Promoções sem datas.** Sem datas de vigência, `is_active` é a única fonte de verdade.
- **Divergências não resolvidas na origem.** Telefone, status do produto 130 e totais dos pedidos
  3 e 20 precisariam ser confirmados com a loja. Com mais tempo, o relatório de qualidade viraria
  uma fila de revisão para a equipe.

## Uso de assistentes de código

Usei o **Claude Code** (Anthropic) dentro do VS Code como par de programação:

1. **Análise inicial e segurança.** Pedi uma análise dos arquivos do desafio, incluindo uma
   varredura por conteúdo malicioso ou prompts escondidos. Foram verificados JavaScript e ações
   automáticas nos PDFs, texto invisível, caracteres Unicode ocultos e tentativas de prompt
   injection nos CSVs. Nada foi encontrado.
2. **Levantamento das inconsistências.** O assistente listou as anomalias dos dados e do manual.
   Eu revisei cada uma e decidi como tratá-la (tabelas acima).
3. **Implementação.** O pipeline e os testes foram gerados com o assistente, a partir das decisões
   acima, e revisados por mim. O próprio processo pegou erros: um teste com valor esperado
   errado e uma contagem de produtos incorreta foram corrigidos durante a revisão.
