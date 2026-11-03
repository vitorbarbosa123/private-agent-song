# Empório da Música — Agente de Atendimento

Protótipo de um agente de atendimento por mensagens de texto para a **Empório da Música**, loja
fictícia de instrumentos musicais em Campo Grande/MS. Desenvolvido como desafio técnico para a
vaga de AI Engineer na Artefact.

> **Status:** em desenvolvimento. Concluídos: **tratamento dos dados**, **camada de acesso aos
> dados** e **configuração do modelo**. As seções sobre o agente serão preenchidas conforme a
> implementação avançar.

## Sumário

- [Como rodar](#como-rodar)
- [Modelo de linguagem: como trocar](#modelo-de-linguagem-como-trocar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Tratamento dos dados](#tratamento-dos-dados)
- [Interpretações do manual de políticas](#interpretações-do-manual-de-políticas)
- [Camada de acesso aos dados](#camada-de-acesso-aos-dados)
- [Limitações conhecidas](#limitações-conhecidas)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)

## Como rodar

Pré-requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # cria o ambiente virtual e instala as dependências
cp .env.example .env       # e preencha LLM_API_KEY (chave do OpenRouter)
uv run emporio-clean-data  # trata os dados brutos e grava os artefatos em data/processed/
uv run emporio-llm-check   # confere a configuração e faz uma chamada mínima ao modelo
uv run pytest              # roda os testes (não fazem chamadas ao modelo)
```

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

Exemplo com modelo local, sem chave: `LLM_BASE_URL=http://localhost:11434/v1` e
`LLM_MODEL=llama3.1`. O comando `uv run emporio-llm-check` mostra a configuração ativa (com a
chave mascarada) e qual modelo de fato atendeu a requisição, o que é útil para confirmar um
fallback.

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
├── policy_rules.py                  # regras de negócio canônicas + conflitos resolvidos do manual
├── repository/                      # consultas fixas, somente leitura, sobre o SQLite tratado
└── data/
    ├── pipeline.py                  # orquestração, escrita dos artefatos e relatório
    ├── products.py                  # catálogo: specs, descrições, disponibilidade
    ├── promotions.py                # promoções ativas e preço vigente
    ├── categories.py · customers.py · orders.py
    ├── policies.py                  # extração do PDF e divisão em seções
    └── issues.py · utils.py · paths.py
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

## Limitações conhecidas

- **Validação de marcas por dicionário.** A detecção de descrições conflitantes usa uma lista de
  marcas e modelos conhecidos. Uma marca nova no catálogo precisa ser adicionada a `BRANDS` em
  `products.py`.
- **Busca textual por regras.** Sinônimos ("acústico" vs. "folk", "elétrico" vs.
  "eletroacústico") não são tratados. Com um catálogo maior, valeria uma busca híbrida (BM25 +
  embeddings).
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
