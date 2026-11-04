# Devolução por arrependimento (dentro do prazo)

> **O que este exemplo mostra:** Situação não trivial: verificação de identidade antes de consultar o pedido, cálculo do prazo de 7 dias pela política (a partir da previsão de entrega) e encaminhamento para a equipe com protocolo, só depois da concordância da cliente.
>
> Data simulada: sexta-feira, 20/02/2026 10:30 · Modelo: `@preset/emporio-agent → anthropic/claude-haiku-4.5` · Custo: US$ 0.0336
>
> Gerado por `uv run emporio-export-examples` a partir de uma conversa real com o agente.

---

**🙂 Cliente:**

Me arrependi da minha compra, posso devolver meu pedido?

**🎸 Lia:**

Claro, entendo! Posso ajudar a verificar se seu pedido pode ser devolvido.

Para isso, preciso de:
1. **Número do pedido**
2. **Seu e-mail ou telefone** (o mesmo que usou na compra)

Depois que você me passar esses dados, eu consulto o prazo e as condições para você. 😊

---

**🙂 Cliente:**

É o pedido 7, meu email é leticia.rocha@jmail.com

**🎸 Lia:**

Ótima notícia, Leticia! Seu pedido **está dentro do prazo** para devolução por arrependimento. 👍

**Aqui estão os detalhes:**
- **Prazo**: até **24/02/2026** (você tem mais 4 dias)
- **Condições**: o produto precisa estar na embalagem original, sem sinais de uso, com todos os acessórios e manuais
- **Frete**: a loja paga a devolução
- **Reembolso**: volta na mesma forma de pagamento em até 10 dias úteis

**Obs.:** o prazo foi contado pela previsão de entrega (17/02). Se você recebeu em outra data, me avisa que recalculo!

Quer que eu encaminhe seu caso à equipe para gerar a autorização de devolução?

<details><summary>🔧 Ferramentas chamadas: `check_return_eligibility`</summary>

**`check_return_eligibility`**

```json
{"order_id": 7, "email": "leticia.rocha@jmail.com", "reason": "arrependimento"}
```

Resultado:

```json
{
  "status": "ok",
  "eligible": true,
  "decision": "Dentro do prazo de 7 dias corridos do direito de arrependimento.",
  "deadline": "24/02/2026",
  "days_remaining": 4,
  "days_elapsed": 3,
  "date_basis": "previsão de entrega do pedido (data real não registrada): 17/02/2026",
  "conditions": [
    "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
    "Não são elegíveis: instrumentos com personalização ou ajuste sob encomenda (setup, regulagem especial), itens de liquidação com aviso de 'venda final' e boquilhas de instrumentos de sopro (manual 4.4)."
  ],
  "next_steps": [
    "Informe ao cliente o prazo, as condições, que o frete de devolução é por conta da loja e que o reembolso sai na mesma forma de pagamento em até 10 dias úteis.",
    "Depois PERGUNTE se ele quer que você encaminhe à equipe (escalate_to_human) para gerar a autorização de devolução."
  ],
  "policy_sections": [
    "4.1",
    "4.4"
  ],
  "requires_human": true,
  "notes": [
    "A data usada é a PREVISÃO de entrega, não a data real. Diga isso ao cliente (ex.: 'pela previsão de entrega, dia 17/02') e, se ele recebeu em outra data, consulte de novo com received_date."
  ]
}
```

</details>

---

**🙂 Cliente:**

Pode encaminhar sim! Meu nome é Letícia, pode usar o mesmo email.

**🎸 Lia:**

Pronto! Seu caso foi registrado. 

**Protocolo: ATD-00001**

A equipe vai entrar em contato com você **ainda hoje** pelo e-mail ou WhatsApp para gerar a autorização de devolução. Se preferir, você também pode chamar direto no **(67) 3341-4444**.

Mais alguma coisa que eu possa ajudar?

<details><summary>🔧 Ferramentas chamadas: `escalate_to_human`</summary>

**`escalate_to_human`**

```json
{"reason": "troca_ou_devolucao", "customer_name": "Letícia", "order_id": 7, "contact": "leticia.rocha@jmail.com", "summary": "Letícia solicita devolução por arrependimento do pedido 7. Verificado: elegível, dentro do prazo de 7 dias (até 24/02/2026). Produto deve estar na embalagem original, sem uso, com acessórios e manuais. Frete de devolução por conta da loja. Reembolso em até 10 dias úteis na mesma forma de pagamento. Aguarda autorização de devolução."}
```

Resultado:

```json
{
  "status": "created",
  "ticket": "ATD-00001",
  "team_available_now": true,
  "expected_response": "a equipe entra em contato ainda hoje, durante o expediente",
  "notes": [
    "Informe o protocolo e o prazo ao cliente. Não prometa solução: quem decide é a equipe.",
    "Se o cliente preferir, ele também pode chamar no WhatsApp (67) 3341-4444."
  ]
}
```

</details>
