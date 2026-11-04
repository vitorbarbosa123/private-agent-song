# Operação: observabilidade e CI

[← Voltar ao README](../README.md)

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

O workflow [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) roda a cada push e pull
request, **sem precisar de chave de API**:

| Job | Passos |
|---|---|
| `test` | `ruff check` (lint); `pytest` (300 testes, com modelo roteirizado); regenera os dados tratados e exige que o relatório de qualidade versionado esteja idêntico (garante que o pipeline é determinístico e que o relatório não ficou desatualizado); avaliação da busca no conjunto de validação em modo BM25 |
| `docker` | Build das imagens; testes dentro do container; sobe a interface web e espera o healthcheck |

As avaliações que chamam o modelo (`emporio-eval-agent`, embeddings) ficam fora do CI: custam
crédito e variam entre execuções. Elas são rodadas sob demanda, e os resultados ficam em
`evals/results/`.
