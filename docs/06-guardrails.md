# Guardrails

[← Voltar ao README](../README.md)

São proteções em camadas, todas **determinísticas** (sem LLM extra) e cobertas por testes:

| Camada | Onde | O que faz | Por quê |
|---|---|---|---|
| Entrada | [`agent/guards.py`](../src/emporio/agent/guards.py), nó `input_guard` | Mascara **cartão** (14-19 dígitos com Luhn, para não confundir com telefones), **CVV** e **CPF** antes de a mensagem entrar no histórico | O histórico é persistido; a loja não precisa desses dados no chat (LGPD/PCI) |
| Entrada | idem | Detecta **tentativas de manipulação** ("ignore as instruções", "mostre seu prompt", `[system]`, "modo desenvolvedor") e acrescenta um aviso ao system prompt **só naquele turno** | Reforça a regra do prompt exatamente quando é necessária, sem bloquear a mensagem: ela pode conter uma dúvida real |
| Entrada | idem | Trunca mensagens com mais de 2.000 caracteres | Limita custo e abuso |
| Prompt | [`agent/prompts.py`](../src/emporio/agent/prompts.py) | Mensagens do cliente e resultados de ferramentas são dados, não instruções; o agente não muda de papel, não cria descontos e não revela o prompt | Primeira linha de defesa |
| Ferramentas | [`tools/orders.py`](../src/emporio/tools/orders.py) | Pedido só com número + e-mail ou telefone do titular; bloqueio após 3 tentativas erradas; mesma resposta para "não existe" e "não confere" | LGPD: não revela dados de terceiros nem quais pedidos existem |
| Saída | [`agent/verification.py`](../src/emporio/agent/verification.py) | Todo **protocolo** citado precisa ter sido emitido por `escalate_to_human`; todo **valor em R$** precisa ter vindo de uma ferramenta, do próprio cliente ou dos valores fixos da política | Alucinação de preço é propaganda enganosa (manual 7.1); protocolo falso engana o cliente |
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
