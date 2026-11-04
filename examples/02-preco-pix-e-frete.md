# Preço, desconto no PIX e entrega fora de Campo Grande

> **O que este exemplo mostra:** Consulta de preço (ignorando uma promoção inativa), economia no PIX vinda da ferramenta e regras de frete para outra cidade, sem inventar valor.
>
> Data simulada: segunda-feira, 02/03/2026 10:30 · Modelo: `@preset/emporio-agent → anthropic/claude-haiku-4.5` · Custo: US$ 0.0311
>
> Gerado por `uv run emporio-export-examples` a partir de uma conversa real com o agente.

---

**🙂 Cliente:**

Quanto custa o Takamine GD20?

**🎸 Lia:**

O **Takamine GD20 Dreadnought Natural** custa **R$ 2.199,00**.

Se pagar no PIX, sai por **R$ 2.089,05** (economiza R$ 109,95).

É um violão com tampo sólido em cedro, fundo e laterais em sapele, cordas de aço — ótimo para fingerstyle. Tá disponível pra compra agora 🎸

Quer saber mais sobre ele ou precisa de ajuda com parcelamento?

<details><summary>🔧 Ferramentas chamadas: `get_product_details`</summary>

**`get_product_details`**

```json
{"name": "Takamine GD20"}
```

Resultado:

```json
{
  "found": true,
  "product": {
    "product_id": 95,
    "name": "Takamine GD20 Dreadnought Natural",
    "brand": "Takamine",
    "category": "Violões",
    "availability": "disponível",
    "available_for_sale": true,
    "price": {
      "list_price": "R$ 2.199,00",
      "pix_price": "R$ 2.089,05",
      "pix_savings": "R$ 109,95",
      "current_price_brl": 2199.0
    },
    "description": "Violão dreadnought Takamine com tampo sólido em cedro. Excelente para fingerstyle com timbre quente e definido.",
    "specs": {
      "tampo": "Cedro Sólido",
      "fundo e laterais": "Sapele",
      "braço": "Mogno",
      "cordas": "aço",
      "escala": "650mm",
      "eletrônica/captação": "não",
      "cor": "Natural"
    }
  },
  "candidates": [],
  "alternatives": [],
  "notes": []
}
```

</details>

---

**🙂 Cliente:**

E se eu pagar no PIX, quanto economizo?

**🎸 Lia:**

Você economiza **R$ 109,95** pagando no PIX!

O preço normal é R$ 2.199,00 e no PIX fica R$ 2.089,05.

Posso ajudar em mais alguma coisa?

---

**🙂 Cliente:**

Vocês entregam em Dourados?

**🎸 Lia:**

Sim, a gente entrega em Dourados! 

Temos três opções de transportadora:
- **PAC (Correios)**: 5 a 12 dias úteis
- **SEDEX (Correios)**: 2 a 5 dias úteis
- **Jadlog**: 3 a 8 dias úteis

O valor do frete é calculado no checkout de acordo com seu CEP, peso e dimensões do produto. Todos os envios têm rastreamento e seguro contra extravio e avaria.

Quer prosseguir com o Takamine GD20?

<details><summary>🔧 Ferramentas chamadas: `shipping_quote`</summary>

**`shipping_quote`**

```json
{"city": "Dourados", "product_ids": [95]}
```

Resultado:

```json
{
  "region": "Dourados (fora de Campo Grande)",
  "carriers": [
    "PAC (Correios): 5 a 12 dias úteis",
    "SEDEX (Correios): 2 a 5 dias úteis",
    "Jadlog (.package): 3 a 8 dias úteis"
  ],
  "notes": [
    "O valor do frete é calculado no checkout pelo CEP, peso e dimensões; não informe valores.",
    "Todos os envios têm rastreamento e seguro contra extravio e avaria."
  ]
}
```

</details>
