# Avaliação do agente

[← Voltar ao README](../README.md)

```bash
uv run emporio-eval-agent                     # só verificações determinísticas (~US$ 0,30)
uv run emporio-eval-agent --judge --judge-model google/gemini-2.5-pro   # + avaliador LLM
uv run emporio-eval-agent --calibrate-judge   # mede o próprio avaliador
uv run emporio-eval-agent --model <outro>     # compara outro modelo para o agente
```

São [28 conversas de teste](../evals/agent_scenarios.yaml) em 13 categorias: os 4 cenários do
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

**Resultado final** ([relatório completo](../evals/results/agent_eval.md)), com o agente
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
  um [conjunto de calibração](../evals/judge_calibration.yaml) com 12 respostas de veredito conhecido
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

## Comparação de modelos

Como o modelo é trocável por configuração, a mesma avaliação foi rodada com outros modelos do
OpenRouter que suportam ferramentas com a política de retenção zero de dados do workspace. O
avaliador é o mesmo para todos (`google/gemini-2.5-pro`, calibrado). Relatórios em
[`evals/results/models/`](../evals/results/models/).

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
