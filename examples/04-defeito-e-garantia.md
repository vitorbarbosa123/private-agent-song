# Defeito depois de 30 dias (garantia legal) e encaminhamento

> **O que este exemplo mostra:** Situação não trivial: fora dos 30 dias de troca direta, mas dentro da garantia legal de 90 dias. A assistente aplica a interpretação documentada para o conflito entre as seções 4.2 e 8.1 do manual e registra o caso para a equipe.
>
> Data simulada: quarta-feira, 15/04/2026 15:00 · Modelo: `@preset/emporio-agent → anthropic/claude-haiku-4.5` · Custo: US$ 0.0336
>
> Gerado por `uv run emporio-export-examples` a partir de uma conversa real com o agente.

---

**🙂 Cliente:**

Oi, meu ukulele do pedido 7 começou a trastejar e o braço empenou. Ainda tem garantia?

**🎸 Lia:**

Oi! Desculpa com o problema no seu ukulele. Vou verificar a garantia e se você pode fazer uma troca ou reparo.

Preciso confirmar alguns dados antes: qual é o seu e-mail ou telefone que está cadastrado no pedido 7?

---

**🙂 Cliente:**

Meu email é leticia.rocha@jmail.com

**🎸 Lia:**

Ótima notícia, Leticia! Seu ukulele **está dentro da garantia legal de 90 dias**. 

Aqui está a situação:
- **Prazo**: você tem até **18/05/2026** para solicitar o reparo ou troca (faltam 33 dias)
- **Como funciona**: como passou dos 30 dias de troca direta, a loja intermedia o reparo ou troca com o fabricante
- **O que a garantia cobre**: defeitos de fabricação. Não cobre mau uso, quedas, umidade excessiva, modificações não autorizadas ou desgaste natural

Só um detalhe: o prazo foi contado pela **previsão de entrega do seu pedido (17/02/2026)**. Você recebeu o ukulele nessa data ou em outra?

Depois que você confirmar, vou registrar o caso para a equipe cuidar do reparo ou troca com o fabricante. Eles vão pedir fotos ou vídeo do defeito para avaliar.

<details><summary>🔧 Ferramentas chamadas: `check_return_eligibility`</summary>

**`check_return_eligibility`**

```json
{"order_id": 7, "email": "leticia.rocha@jmail.com", "reason": "defeito"}
```

Resultado:

```json
{
  "status": "ok",
  "eligible": true,
  "decision": "Fora dos 30 dias de troca direta, mas dentro da garantia legal de 90 dias: a loja intermedia o reparo ou troca com o fabricante.",
  "deadline": "18/05/2026",
  "days_remaining": 33,
  "days_elapsed": 71,
  "date_basis": "previsão de entrega do pedido (data real não registrada): 17/02/2026",
  "conditions": [
    "Não cobre mau uso, quedas, umidade excessiva, modificações não autorizadas, desgaste natural (trastes, cordas, feltros) nem danos apenas estéticos."
  ],
  "next_steps": [
    "Informe a situação (prazo e cobertura) e peça fotos ou vídeo do defeito.",
    "Com a concordância do cliente, registre com escalate_to_human (reason='defeito'), incluindo este resultado no resumo."
  ],
  "policy_sections": [
    "4.2",
    "8"
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

Pode registrar, por favor. Sou a Letícia e o contato é o mesmo email.

**🎸 Lia:**

Pronto! Seu caso foi registrado com sucesso. 

**Protocolo: ATD-00001**

A equipe vai entrar em contato com você **ainda hoje** pelo e-mail para avaliar o defeito e providenciar o reparo ou troca com o fabricante. Se preferir, você também pode chamar direto no WhatsApp **(67) 3341-4444**.

Tem mais alguma coisa que eu possa ajudar? 🎵

<details><summary>🔧 Ferramentas chamadas: `escalate_to_human`</summary>

**`escalate_to_human`**

```json
{"reason": "defeito", "customer_name": "Letícia", "order_id": 7, "contact": "leticia.rocha@jmail.com", "summary": "Ukulele do pedido 7 com defeito de fabricação: trastes começaram a trastejar e braço empenou. Cliente está dentro da garantia legal de 90 dias (prazo até 18/05/2026). Fora dos 30 dias de troca direta, então será intermediado reparo/troca com fabricante. Cliente autoriza o registro e solicita que a equipe proceda com a avaliação."}
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
