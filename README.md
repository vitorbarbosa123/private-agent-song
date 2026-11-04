# Empório da Música — Agente de Atendimento

Protótipo de um agente de atendimento por mensagens de texto para a **Empório da Música**, loja
fictícia de instrumentos musicais em Campo Grande/MS. Desenvolvido como desafio técnico para a
vaga de AI Engineer na Artefact.

> **Status:** em desenvolvimento. Concluídos: **tratamento dos dados**, **camada de acesso aos
> dados**, **configuração do modelo**, **ferramentas do agente**, **busca no manual (RAG)**,
> **agente com interface de terminal**, **histórico persistente com encaminhamento para humanos**,
> **guardrails**, **avaliação de ponta a ponta** e **interface web em containers**. As seções sobre o agente serão preenchidas conforme a
> implementação avançar.

## Sumário

- [Como rodar](#como-rodar)
- [Conversas de exemplo](#conversas-de-exemplo)
- [Interface web](#interface-web)
- [Conversando pelo terminal](#conversando-pelo-terminal)
- [API REST](#api-rest)
- [Modelo de linguagem: como trocar](#modelo-de-linguagem-como-trocar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Tratamento dos dados](#tratamento-dos-dados)
- [Interpretações do manual de políticas](#interpretações-do-manual-de-políticas)
- [Camada de acesso aos dados](#camada-de-acesso-aos-dados)
- [Ferramentas do agente](#ferramentas-do-agente)
- [Busca no manual de políticas (RAG)](#busca-no-manual-de-políticas-rag)
- [Arquitetura do agente](#arquitetura-do-agente)
- [Guardrails](#guardrails)
- [Avaliação do agente](#avaliação-do-agente)
- [Observabilidade (Langfuse)](#observabilidade-langfuse)
- [Integração contínua](#integração-contínua)
- [Limitações conhecidas](#limitações-conhecidas)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)

## Como rodar

### Com Docker (recomendado)

Pré-requisitos: Docker com Compose v2.

```bash
cp .env.example .env              # preencha LLM_API_KEY (chave do OpenRouter)
docker compose up --build         # web em http://localhost:8501 e API em http://localhost:8710/docs
```

Os demais comandos rodam em containers da mesma imagem:

```bash
docker compose run --rm chat                     # chat no terminal (aceita --now, --debug, --session…)
docker compose run --rm tests                    # testes (não precisam de chave de API)
docker compose run --rm llm-check                # confere a configuração do modelo
docker compose run --rm eval --judge --judge-model google/gemini-2.5-pro   # avaliação do agente
docker compose run --rm eval-retrieval --dataset holdout                   # avaliação da busca
docker compose run --rm handoffs                 # painel da equipe no terminal
```

A imagem gera os dados tratados durante o build (o pipeline é determinístico e não precisa de
chave). Histórico das conversas e atendimentos ficam no volume `emporio-state`, compartilhado
entre a interface web e o terminal. O container roda com um usuário sem privilégios, e o `.env`
nunca entra na imagem: é lido em tempo de execução.

### Localmente, com uv

Pré-requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # cria o ambiente virtual e instala as dependências
cp .env.example .env       # e preencha LLM_API_KEY (chave do OpenRouter)
uv run emporio-clean-data  # trata os dados brutos e grava os artefatos em data/processed/
uv run streamlit run src/emporio/ui/app.py   # interface web
uv run emporio-llm-check   # confere a configuração e faz uma chamada mínima ao modelo
uv run emporio-eval-retrieval [--dataset holdout]  # avalia a busca no manual de políticas
uv run emporio-chat        # conversa com a assistente no terminal
uv run emporio-eval-agent [--judge]  # avaliação de ponta a ponta com 28 conversas de teste
uv run emporio-handoffs    # painel da equipe: atendimentos encaminhados pela assistente
uv run pytest              # roda os testes (não fazem chamadas ao modelo)
```

## Conversas de exemplo

Cinco conversas reais com a assistente, em [`examples/`](examples/):

| Conversa | O que mostra |
|---|---|
| [Catálogo, indicação e parcelamento](examples/01-catalogo-e-indicacao.md) | Busca com filtro de preço, indicação para iniciante, parcelamento pelas faixas da política |
| [Preço, PIX e entrega](examples/02-preco-pix-e-frete.md) | Preço sem a promoção inativa, economia no PIX, frete para outra cidade sem inventar valor |
| [Devolução por arrependimento](examples/03-devolucao-por-arrependimento.md) | **Não trivial:** verificação de identidade, prazo de 7 dias calculado pela política, encaminhamento com protocolo após concordância |
| [Defeito e garantia legal](examples/04-defeito-e-garantia.md) | **Não trivial:** fora dos 30 dias de troca direta, dentro dos 90 de garantia legal (conflito do manual resolvido) |
| [Limites e segurança](examples/05-limites-e-seguranca.md) | Loja fechada no domingo, acessórios, tentativa de manipulação, dados de cartão removidos |

Os exemplos são **gerados por script** (`uv run emporio-export-examples`) a partir de um roteiro
de mensagens do cliente ([`evals/example_conversations.yaml`](evals/example_conversations.yaml)).
As respostas e as ferramentas chamadas são as do agente real, e cada resposta traz um bloco
expansível com as ferramentas usadas, os parâmetros e o resultado.

Revisar os exemplos gerados revelou duas falhas, corrigidas na causa antes de regerar todos:
numa mensagem com duas perguntas ("qual o endereço? estão abertos?"), a assistente respondia só a
segunda; e, fora do expediente, dizia "ajudo quando puder", como se ela também tivesse horário.
O prompt passou a exigir que todas as perguntas sejam respondidas e a deixar claro que só a
equipe humana tem horário. A ferramenta de horário passou a devolver também o endereço.

## Interface web

`docker compose up` (ou `uv run streamlit run src/emporio/ui/app.py`) abre a interface em
http://localhost:8501. Ela segue o modelo dos chats de IA atuais:

- **Conversas na barra lateral,** com título (a primeira pergunta). Dá para criar uma nova,
  retomar qualquer conversa anterior e apagar a atual (direito de exclusão, LGPD).
- **Histórico persistente** no mesmo SQLite usado pelo terminal.
- **Ferramentas chamadas em cada resposta:** um painel expansível mostra quais ferramentas a
  assistente usou, com os parâmetros enviados e o resultado recebido. Facilita entender e
  auditar as decisões do agente. Pode ser desligado na barra lateral.
- **Sugestões iniciais** com as quatro perguntas do enunciado.
- **Simulação de data e hora,** útil porque os pedidos da base são de 2025-2026 (ex.: testar o
  prazo de devolução ou a loja fechada no domingo).
- **Página "Atendimentos":** a equipe vê e encerra os casos encaminhados pela assistente.

A interface foi testada de ponta a ponta com o `AppTest` do Streamlit dentro do container:
clique em uma sugestão, resposta real do modelo, painel de ferramentas, conversa na barra lateral
e um segundo turno usando o contexto ("e em quantas vezes posso pagar *ele*?").

## Conversando pelo terminal

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
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | Ativam o rastreamento no Langfuse (ver [Observabilidade](#observabilidade-langfuse)) | desligado |
| `LLM_PROMPT_CACHE` | Marca a parte fixa do system prompt para cache do provedor | `true` |
| `EMPORIO_API_KEY` | Se definida, a API REST exige o cabeçalho `X-API-Key` | sem autenticação |
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
├── agent/                           # grafo LangGraph, prompt, memória, histórico e verificação
├── ui/app.py                        # interface web (Streamlit)
├── handoff.py                       # registro de atendimentos encaminhados + painel da equipe
├── cli.py                           # interface de terminal (emporio-chat)
├── api.py                           # API REST (FastAPI)
├── observability.py · privacy.py    # rastreamento no Langfuse e mascaramento de dados
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
evals/                               # conjuntos de avaliação (busca, agente, calibração do avaliador)
│   └── results/agent_eval.md        # último relatório da avaliação do agente
tests/
Dockerfile · docker-compose.yml      # imagem (runtime e testes) e serviços
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

## API REST

`docker compose up` também sobe uma API (FastAPI) em http://localhost:8710, com documentação
interativa em `/docs`. Ela é a porta de integração com canais reais (WhatsApp Business, site, CRM)
e usa as mesmas conversas e atendimentos da interface web e do terminal.

| Endpoint | Função |
|---|---|
| `POST /conversations` | Cria uma conversa |
| `GET /conversations` | Lista conversas (com título) |
| `POST /conversations/{id}/messages` | Envia a mensagem do cliente e devolve a resposta; `?include_tools=true` inclui as ferramentas chamadas |
| `GET /conversations/{id}` | Histórico em turnos |
| `DELETE /conversations/{id}` | Apaga a conversa (LGPD) |
| `GET /handoffs`, `POST /handoffs/{id}/close` | Atendimentos encaminhados para a equipe |
| `GET /health` | Healthcheck (público) |

```bash
curl -s -X POST localhost:8710/conversations/minha-conversa/messages \
  -H 'Content-Type: application/json' -d '{"message": "Quanto custa o Takamine GD20?"}'
```

Com `EMPORIO_API_KEY` definida, todas as rotas (exceto `/health`) exigem o cabeçalho
`X-API-Key`. No Compose a porta fica ligada só ao `localhost` e é configurável
(`EMPORIO_API_PORT`). Falhas do provedor não viram erro HTTP: a resposta traz a mensagem de
fallback com `"error": true`, para o canal decidir o que fazer.

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

## Guardrails

São proteções em camadas, todas **determinísticas** (sem LLM extra) e cobertas por testes:

| Camada | Onde | O que faz | Por quê |
|---|---|---|---|
| Entrada | [`agent/guards.py`](src/emporio/agent/guards.py), nó `input_guard` | Mascara **cartão** (14-19 dígitos com Luhn, para não confundir com telefones), **CVV** e **CPF** antes de a mensagem entrar no histórico | O histórico é persistido; a loja não precisa desses dados no chat (LGPD/PCI) |
| Entrada | idem | Detecta **tentativas de manipulação** ("ignore as instruções", "mostre seu prompt", `[system]`, "modo desenvolvedor") e acrescenta um aviso ao system prompt **só naquele turno** | Reforça a regra do prompt exatamente quando é necessária, sem bloquear a mensagem: ela pode conter uma dúvida real |
| Entrada | idem | Trunca mensagens com mais de 2.000 caracteres | Limita custo e abuso |
| Prompt | [`agent/prompts.py`](src/emporio/agent/prompts.py) | Mensagens do cliente e resultados de ferramentas são dados, não instruções; o agente não muda de papel, não cria descontos e não revela o prompt | Primeira linha de defesa |
| Ferramentas | [`tools/orders.py`](src/emporio/tools/orders.py) | Pedido só com número + e-mail ou telefone do titular; bloqueio após 3 tentativas erradas; mesma resposta para "não existe" e "não confere" | LGPD: não revela dados de terceiros nem quais pedidos existem |
| Saída | [`agent/verification.py`](src/emporio/agent/verification.py) | Todo **protocolo** citado precisa ter sido emitido por `escalate_to_human`; todo **valor em R$** precisa ter vindo de uma ferramenta, do próprio cliente ou dos valores fixos da política | Alucinação de preço é propaganda enganosa (manual 7.1); protocolo falso engana o cliente |
| Saída | `agent_node` | Se a resposta reprova na verificação, o modelo recebe uma correção, que não fica no histórico nem é vista pelo cliente, e reescreve. Se insistir, o cliente recebe uma mensagem segura com o contato da loja | Corrige sem expor o mecanismo ao cliente |
| Saída | `agent_node` | Se o cliente enviou cartão ou CPF e a resposta não toca no assunto, um aviso fixo é acrescentado | Nos testes, o modelo ignorava a orientação do prompt; o aviso precisa ser garantido |

**Por que não um classificador com LLM na entrada.** O plano inicial previa um segundo modelo
para classificar cada mensagem (no escopo, fora do escopo, injeção). Nos testes reais, o modelo
principal já recusou temas fora do escopo e resistiu a injeções de prompt. Um classificador
acrescentaria latência e custo a **toda** mensagem para um ganho pequeno. Os riscos que o prompt
**não** cobre de forma confiável (vazamento de dados sensíveis, valores e protocolos inventados)
foram tratados com regras determinísticas, que são baratas, previsíveis e testáveis.

**O que os testes ao vivo mostraram e como foi corrigido:**

- O modelo calculou por conta própria a "economia de R$ 109,95" no PIX. A verificação de preços
  pegou isso. Como a pergunta do cliente é legítima, as ferramentas passaram a devolver a
  economia já calculada (`pix_savings`, `promotion.savings`).
- Na primeira versão, a correção interna vazava para o cliente ("Você tem razão! Peço desculpas,
  não deveria ter calculado…"). A instrução de correção passou a dizer explicitamente que o
  cliente não a vê.
- O aviso de "não envie dados de cartão" era ignorado pelo modelo, e por isso passou a ser
  determinístico.

## Avaliação do agente

```bash
uv run emporio-eval-agent                     # só verificações determinísticas (~US$ 0,30)
uv run emporio-eval-agent --judge --judge-model google/gemini-2.5-pro   # + avaliador LLM
uv run emporio-eval-agent --calibrate-judge   # mede o próprio avaliador
uv run emporio-eval-agent --model <outro>     # compara outro modelo para o agente
```

São [28 conversas de teste](evals/agent_scenarios.yaml) em 13 categorias: os 4 cenários do
enunciado, catálogo, preços e promoções, pagamento, frete, pedidos, devoluções, políticas,
horário, encaminhamento, multi-turno, fora do escopo e segurança. A avaliação tem duas camadas:

1. **Verificações determinísticas por turno.** Ferramentas que devem ou não ser chamadas e
   trechos obrigatórios ou proibidos na resposta (ex.: "R$ 2.199,00" sim; o número divergente do
   WhatsApp, não; nada do pedido quando o e-mail não confere). Pegam erros objetivos sem
   subjetividade.
2. **Avaliador LLM (LLM-as-judge).** Notas de 1 a 5 para tom, aderência à política e utilidade,
   com o objetivo do cenário e os dados das ferramentas como referência. Usei um modelo de
   **outra família** (Gemini) para avaliar o agente (Claude), reduzindo o viés de um modelo
   favorecer as próprias respostas.

**Resultado final** ([relatório completo](evals/results/agent_eval.md)), com o agente
`anthropic/claude-haiku-4.5` (via preset) e o avaliador `google/gemini-2.5-pro`:

| Métrica | Resultado |
|---|---|
| Verificações determinísticas | 28/28 cenários (100%) |
| Seleção de ferramentas (por turno) | 100% |
| Avaliador: tom / política / utilidade (média 1-5) | 5,0 / 4,93 / 4,96 |
| Cenários aprovados (verificações + todas as notas ≥ 4) | 27/28 (96%) |
| Latência média por turno | 3,4 s |
| Custo da execução completa (31 turnos) | ~US$ 0,32 |

**Como chegamos aqui: o que a avaliação revelou.**

- **Primeira execução (26/28 nas verificações).** Uma falha era real: para "vocês entregam em
  Dourados?", o agente perguntava qual produto em vez de responder, porque a descrição da
  ferramenta de frete não deixava claro que só a cidade é obrigatória. A outra era do meu
  cenário: o "cliente" pedia para registrar uma reclamação sem contar o que houve, e pedir
  detalhes era o comportamento correto. Ajustei o cenário e deixo isso registrado.
- **O avaliador também precisa ser avaliado.** Na primeira versão, ele reprovou 12 cenários
  corretos: leu "nunca informar preço que não venha do sistema" como "nunca informar preço". Criei
  um [conjunto de calibração](evals/judge_calibration.yaml) com 12 respostas de veredito conhecido
  (preço inventado, PIX somado à promoção, vazamento de dados de pedido, desconto prometido, prazo
  inventado, tom robótico e respostas boas) e reescrevi o prompt dele até acertar todas. Os dois
  avaliadores testados acertam 12/12 (`gemini-2.5-flash` e `gemini-2.5-pro`).
- **Erros meus no contexto do avaliador.** Faltava o endereço da loja nos dados institucionais,
  os dados das ferramentas eram truncados (as alternativas sugeridas ficavam de fora) e ele não
  sabia a data da conversa (achou que "amanhã, sábado 04/04" era inventado).
- **Problemas reais do agente que a avaliação pegou e foram corrigidos:**
  - informar o status do pedido atrasado em vez de encaminhar direto sem perguntar;
  - não oferecer "encomendas", que a loja não faz (a orientação tinha vindo de uma nota da
    minha própria ferramenta);
  - sugerir um violão clássico de nylon como alternativa a um de aço (as alternativas agora
    priorizam o mesmo tipo de corda e de eletrônica);
  - não alertar sobre frete especial para itens grandes fora de Campo Grande;
  - o aviso de cartão era "satisfeito" por qualquer menção à palavra "cartão" (ex.: "pague no
    PIX, cartão ou boleto"); agora exige uma orientação explícita.

### Comparação de modelos

Como o modelo é trocável por configuração, a mesma avaliação foi rodada com outros modelos do
OpenRouter que suportam ferramentas com a política de retenção zero de dados do workspace. O
avaliador é o mesmo para todos (`google/gemini-2.5-pro`, calibrado). Relatórios em
[`evals/results/models/`](evals/results/models/).

| Modelo do agente | Aprovados | Verificações determinísticas | Tom / política / utilidade | Latência média | Custo (28 cenários) |
|---|---:|---:|---|---:|---:|
| `anthropic/claude-haiku-4.5` (preset atual) | 27/28 | 28/28 | 5,0 / 4,93 / 4,96 | 3,6 s | US$ 0,326 |
| `google/gemini-2.5-flash` | **28/28** | 28/28 | 5,0 / 5,0 / 4,89 | **2,3 s** | **US$ 0,029** |
| `openai/gpt-oss-120b` (pesos abertos) | 26/28 | 26/28 | 4,96 / 4,79 / 4,79 | 9,2 s | US$ 0,005 |

**Leitura.**

- O **Gemini 2.5 Flash** empatou ou superou o Haiku com **11 vezes menos custo** e
  latência menor. As respostas dele são mais curtas (utilidade 4,89), o que combina com o tom de
  WhatsApp, mas detalha menos.
- O **gpt-oss-120b** é barato e de pesos abertos (poderia rodar na infraestrutura da loja), mas
  é lento e teve duas falhas reais: escreveu um valor no formato americano ("R$ 1,000"), que a
  verificação de preços barrou, e omitiu as transportadoras para Dourados.
- **Ressalva:** o avaliador é da mesma família do Gemini Flash e pode favorecê-lo. A checagem
  cruzada (reavaliar as respostas gravadas do Flash com um avaliador Claude, via `--rescore
  --judge`) e a execução do `claude-sonnet-4.5` ficaram pendentes: o limite diário de gastos do
  workspace no OpenRouter foi atingido durante a comparação. Por isso o preset continua no Haiku;
  se a checagem cruzada confirmar o resultado, trocar para o Flash é só mudar o preset, sem código.

**Verificações rígidas demais.** A comparação revelou falsos negativos nas minhas expectativas:
"até 4 vezes" não casava com "4x", "abrimos amanhã" (num domingo) não casava com "segunda", "só
vendemos instrumentos" não casava com "acessório", e "3341‑4444" escrito com hífen Unicode
(U+2011) não casava com o hífen comum. Corrigi os cenários e a normalização, e reavaliei as
respostas gravadas com `--rescore`, que reaplica as verificações sem chamar o agente de novo.

**Variação entre execuções.** Rodando os mesmos cenários várias vezes, o conjunto de
reprovações muda (ex.: a falha restante, omitir que o prazo de devolução foi contado pela
*previsão* de entrega, nem sempre acontece). Um resultado isolado não deve ser lido como
definitivo. Com mais tempo, rodaria cada cenário N vezes e reportaria a taxa de aprovação.

**Risco de sobreajuste.** Corrigi o agente olhando falhas destes mesmos cenários. Diferente da
busca no manual, aqui não há um conjunto separado de validação; por isso parei de iterar na
última falha em vez de ajustar até 100%. Um próximo passo seria escrever cenários novos (ou
usar conversas reais) para medir a generalização.

## Observabilidade (Langfuse)

Cada mensagem do cliente vira um **trace no [Langfuse](https://langfuse.com)**, agrupado por
conversa (sessão). O trace mostra o caminho pelo grafo: guardrail de entrada, cada chamada ao
modelo (com tokens e latência), cada ferramenta (com parâmetros e resultado) e a resposta final.
Cada trace também recebe **scores** com os indicadores que o projeto já mede:

| Score | O que indica |
|---|---|
| `fallback` | A resposta foi a mensagem de erro/segurança (falha do provedor, loop, dado não verificado) |
| `ferramentas_chamadas` | Quantas ferramentas foram usadas na mensagem |
| `correcoes_da_verificacao` | Quantas vezes a verificação de saída mandou o modelo corrigir um preço ou protocolo (com o detalhe no comentário) |
| `guardrail_entrada` | Alertas do guardrail de entrada: `card`, `cpf`, `injection`, `truncated` |
| `custo_provedor_usd` | Custo informado pelo OpenRouter |

Com isso dá para responder, em produção: quais perguntas estão caindo no fallback? com que
frequência o modelo inventa preços? quantas tentativas de manipulação por dia? quanto custa cada
conversa?

**Langfuse local, sem criar conta.** O Compose inclui um Langfuse completo (perfil
`observability`), com organização, projeto, chaves e usuário criados automaticamente:

```bash
docker compose --profile observability up   # agente em :8501 e Langfuse em :3000
```

Descomente as três linhas `LANGFUSE_*` do `.env.example` no seu `.env` e entre em
http://localhost:3000 com `admin@emporio.local` / `emporio-local`. Dentro do Compose, os
containers falam com o Langfuse pela rede interna (`langfuse-web:3000`), já configurado. Sem as
chaves o rastreamento fica desligado e o agente funciona igual.

**Privacidade.** Cartões, e-mails, telefones e CPFs são mascarados **antes** de sair do processo,
com o parâmetro `mask` do SDK. A verificação foi feita direto no banco do Langfuse (ClickHouse):
numa conversa com todos esses dados, nenhum dos 10 registros do trace os continha. Esse teste
pegou uma falha: o número do cartão aparecia em 2 registros, porque o rastreamento captura a
entrada do grafo **antes** do guardrail mascarar a mensagem. A máscara do rastreamento passou a
cobrir cartões também.

## Integração contínua

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda a cada push e pull
request, **sem precisar de chave de API**:

| Job | Passos |
|---|---|
| `test` | `ruff check` (lint); `pytest` (266 testes, com modelo roteirizado); regenera os dados tratados e exige que o relatório de qualidade versionado esteja idêntico (garante que o pipeline é determinístico e que o relatório não ficou desatualizado); avaliação da busca no conjunto de validação em modo BM25 |
| `docker` | Build das imagens; testes dentro do container; sobe a interface web e espera o healthcheck |

As avaliações que chamam o modelo (`emporio-eval-agent`, embeddings) ficam fora do CI: custam
crédito e variam entre execuções. Elas são rodadas sob demanda, e os resultados ficam em
`evals/results/`.

## Limitações conhecidas

- **Guardrails baseados em padrões.** A detecção de manipulação usa expressões regulares em
  português e inglês. Ataques mais elaborados (instruções escondidas, outros idiomas, paráfrases)
  podem passar; nesse caso, o que segura é a regra do prompt e as verificações de saída. A
  verificação de preços só cobre valores escritos com "R$".

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
