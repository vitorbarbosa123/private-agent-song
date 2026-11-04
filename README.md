# Empório da Música — Agente de Atendimento

Agente de atendimento por mensagens de texto para a **Empório da Música**, loja fictícia de
instrumentos musicais em Campo Grande/MS. Desenvolvido como desafio técnico para a vaga de
AI Engineer na Artefact.

A assistente, **Lia**, responde sobre catálogo, preços, promoções, pagamento, frete, pedidos,
trocas, garantia e horários. Ela consulta os dados da loja e o manual de políticas por meio de
ferramentas, verifica as próprias respostas antes de enviá-las e encaminha para a equipe humana
o que não pode resolver.

## Início rápido

```bash
cp .env.example .env        # preencha LLM_API_KEY (chave do OpenRouter)
docker compose up --build   # chat em http://localhost:8501 · API em http://localhost:8710/docs
```

Outros comandos (terminal, testes, avaliação), execução sem Docker e como trocar o modelo estão
em [Instalação e configuração](docs/01-instalacao.md).

## Destaques

- **Agente LangGraph com 11 ferramentas** (catálogo, pedidos, trocas, pagamento, frete, horário,
  manual, encaminhamento). Preços, prazos e parcelas são calculados no código, nunca pelo modelo.
- **Busca no manual (RAG)** escolhida por avaliação, com um conjunto de validação separado:
  embeddings superaram BM25 e híbrido em perguntas novas.
- **Guardrails em camadas:** dados de cartão e CPF removidos antes de chegar ao modelo; respostas
  com preço ou protocolo que não vieram das ferramentas são corrigidas antes de chegar ao cliente.
- **Avaliação de ponta a ponta:** 28 conversas de teste com verificações automáticas e um
  avaliador LLM calibrado; comparação entre modelos (qualidade × custo × latência).
- **Pronto para operar:** Docker, interface de chat com histórico e inspeção das ferramentas,
  API REST, observabilidade com Langfuse (com dados pessoais mascarados) e CI no GitHub Actions.

## Onde está cada entregável

| O desafio pede | Onde |
|---|---|
| Agente em Python com persona, uso de dados e políticas, e tratamento do fora do escopo | [Arquitetura do agente](docs/04-agente.md) · [Guardrails](docs/06-guardrails.md) |
| Instruções para rodar (ambiente, provedor do modelo, comandos) | [Instalação e configuração](docs/01-instalacao.md) |
| Justificativa das decisões: framework e arquitetura | [Arquitetura do agente](docs/04-agente.md) |
| Justificativa das decisões: LLM e provedor | [Instalação e configuração](docs/01-instalacao.md#modelo-de-linguagem-como-trocar) · [Comparação de modelos](docs/07-avaliacao.md#comparação-de-modelos) |
| Justificativa das decisões: arquitetura de retrieval | [Busca no manual (RAG)](docs/05-rag.md) |
| Justificativa das decisões: estratégia de prompt | [Arquitetura do agente](docs/04-agente.md#arquitetura-do-agente) |
| Justificativa das decisões: tratamento dos dados | [Dados](docs/03-dados.md) |
| Justificativa das decisões: persistência do histórico e interface | [Arquitetura do agente](docs/04-agente.md) · [Interfaces](docs/02-interfaces.md) |
| Limitações conhecidas e o que faria com mais tempo | [Limitações](docs/09-limitacoes.md) |
| Uso de assistentes de código | [Uso de IA](docs/10-uso-de-ia.md) |
| 3 a 5 conversas de exemplo (ao menos uma não trivial) | [Conversas de exemplo](#conversas-de-exemplo) |

## Documentação

| Documento | Conteúdo |
|---|---|
| [01 · Instalação e configuração](docs/01-instalacao.md) | Docker e uv, variáveis de ambiente, OpenRouter e como trocar o modelo |
| [02 · Interfaces](docs/02-interfaces.md) | Chat web (Streamlit), terminal e API REST |
| [03 · Dados](docs/03-dados.md) | Inconsistências tratadas, interpretações do manual de políticas, camada de acesso |
| [04 · Arquitetura do agente](docs/04-agente.md) | Grafo LangGraph, prompt, ferramentas, memória, encaminhamento, cache de prompt |
| [05 · Busca no manual (RAG)](docs/05-rag.md) | Chunking, embeddings vs. BM25 vs. híbrido, avaliação com conjunto de validação |
| [06 · Guardrails](docs/06-guardrails.md) | Proteções de entrada e verificação das respostas |
| [07 · Avaliação](docs/07-avaliacao.md) | Avaliação de ponta a ponta, calibração do avaliador, comparação de modelos |
| [08 · Operação](docs/08-operacao.md) | Observabilidade com Langfuse e integração contínua |
| [09 · Limitações](docs/09-limitacoes.md) | Limitações conhecidas e o que faria com mais tempo |
| [10 · Uso de IA](docs/10-uso-de-ia.md) | Como usei assistentes de código no projeto |

Relatórios gerados pelo próprio projeto:
[qualidade dos dados](data/processed/data_quality_report.md) ·
[avaliação do agente](evals/results/agent_eval.md) ·
[comparação de modelos](evals/results/models/).

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
numa mensagem com duas perguntas ("qual o endereço? estão abertos?"), a assistente respondia só
a segunda; e, fora do expediente, dizia "ajudo quando puder", como se ela também tivesse
horário.

## Estrutura do projeto

```
data/                                # dados brutos da loja (nunca alterados) e processed/ (gerado)
docs/                                # documentação detalhada (ver tabela acima)
examples/                            # conversas de exemplo geradas a partir do agente real
evals/                               # conjuntos de avaliação e resultados (results/)
src/emporio/
├── agent/                           # grafo LangGraph, prompt, memória, guardrails, verificação
├── tools/                           # ferramentas do agente (funções puras + registro LangChain)
├── rag/                             # busca no manual: BM25, embeddings, avaliação
├── repository/                      # consultas fixas, somente leitura, sobre o SQLite tratado
├── data/                            # pipeline de tratamento dos dados
├── evals/                           # avaliação do agente e geração dos exemplos
├── ui/app.py · api.py · cli.py      # interfaces: web, API REST e terminal
├── config.py · llm.py               # configuração (.env) e fábrica do modelo
├── policy_rules.py                  # regras de negócio canônicas e conflitos resolvidos do manual
├── handoff.py                       # atendimentos encaminhados para a equipe
└── observability.py · privacy.py    # Langfuse e mascaramento de dados pessoais
tests/                               # mais de 300 testes, sem chamadas ao modelo
Dockerfile · docker-compose.yml · docker-compose.langfuse.yml · .github/workflows/ci.yml
```
