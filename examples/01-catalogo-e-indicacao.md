# Catálogo, indicação e parcelamento

> **O que este exemplo mostra:** Busca no catálogo com filtro de preço (só itens à venda), indicação para iniciante com base nos dados, e parcelamento calculado pela política (faixas de parcela mínima).
>
> Data simulada: segunda-feira, 02/03/2026 10:30 · Modelo: `@preset/emporio-agent → anthropic/claude-haiku-4.5` · Custo: US$ 0.0439
>
> Gerado por `uv run emporio-export-examples` a partir de uma conversa real com o agente.

---

**🙂 Cliente:**

Oi! Quais opções de violões disponíveis custando até R$1000?

**🎸 Lia:**

Ótimo! Encontrei 12 violões disponíveis até R$ 1000. Aqui estão os principais:

**Cordas de Nylon (Clássicos):**
1. **Tagima Memphis AC-39** — R$ 429,90 (R$ 408,41 no PIX) — Perfeito pra quem tá começando, corpo leve e confortável.
2. **Rozini RC-104** — R$ 459,90 (R$ 436,91 no PIX) — Madeiras nacionais, acabamento caprichado.
3. **Yamaha C40** — R$ 599,90 (R$ 569,91 no PIX) — Clássico confiável, excelente projeção sonora.
4. **Giannini GN-15** — R$ 689,00 (R$ 654,55 no PIX) — Tampo em cedro, sonoridade quente e encorpada.
5. **Yamaha C70** — R$ 849,00 (R$ 806,55 no PIX) — Nível intermediário, tampo em Spruce sólido.

**Cordas de Aço (Folk):**
1. **Shelby SN-100** — R$ 549,00 (R$ 521,55 no PIX) — Visual moderno em preto, versátil.
2. **Giannini GF-1R** — R$ 579,90 (R$ 550,91 no PIX) — Acabamento Sunburst clássico, som equilibrado.
3. **Yamaha F310** — R$ 699,90 (R$ 664,91 no PIX) — Um dos mais vendidos do mundo, robusto e confiável.
4. **Tagima Dallas Tuner** — R$ 749,00 (R$ 711,55 no PIX) — Com afinador integrado, ideal pra acompanhamento vocal.
5. **Shelby SGD-195E** — R$ 799,00 (R$ 759,05 no PIX) — Eletroacústico com captação integrada.

Qual tipo te interessa mais? Ou quer saber mais sobre algum modelo específico?

<details><summary>🔧 Ferramentas chamadas: `search_products`</summary>

**`search_products`**

```json
{"category": "violão", "max_price": 1000, "limit": 10}
```

Resultado:

```json
{
  "total_found": 12,
  "products": [
    {
      "product_id": 83,
      "name": "Tagima Memphis AC-39 Nylon Natural",
      "brand": "Tagima",
      "category": "Violões",
      "availability": "disponível",
      "available_for_sale": true,
      "price": {
        "list_price": "R$ 429,90",
        "pix_price": "R$ 408,41",
        "pix_savings": "R$ 21,49",
        "current_price_brl": 429.9
      },
      "description": "Violão clássico com cordas de nylon, perfeito para quem está começando. Corpo leve e confortável para longas sessões de estudo.",
      "specs": {
        "tampo": "Linden",
        "fundo e laterais": "Linden",
        "braço": "Nato",
        "cordas": "nylon",
        "escala": "650mm",
        "eletrônica/captação": "não",
        "cor": "Natural"
      }
    },
    {
      "product_id": 85,
      "name": "Rozini RC-104 Nylon Estudante",
      "brand": "Rozini",
      "category": "Violões",
      "availability": "disponível",
      "available_for_sale": true,
      "price": {
        "list_price": "R$ 459,90",
        "pix_price": "R$ 436,91",
        "pix_savings": "R$ 22,99",
        "current_price_brl": 459.9
      },
      "description": "Violão clássico de estudo da Rozini, feito com madeiras nacionais. Acabamento caprichado e preço acessível para iniciantes.",
      "specs": {
        "tampo": "Spruce",
        "fundo e laterais": "Sapele",
        "braço": "Nato",
        "cordas": "nylon",
        "escala": "650mm",
        "eletrônica/captação": "não",
        "cor": "Natural"
      }
    },
    {
      "product_id": 89,
      "name": "Shelby SN-100 Folk Aço Preto",
      "brand": "Shelby",
      "category": "Violões",
      "availability": "disponível",
      "available_for_sale": true,
      "price": {
        "list_price": "R$ 549,00",
        "pix_price": "R$ 521,55",
        "pix_savings": "R$ 27,45",
        "current_price_brl": 549.0
      },
      "description": "Violão folk aço com visual moderno em preto. Indicado para quem busca um instrumento versátil com boa relação custo-benefício.",
      "specs": {
        "tampo": "Linden",
        "fundo e laterais": "Linden",
        "braço": "Nato",
        "cordas": "aço",
        "escala": "648mm",
        "eletrônica/captação": "não",
        "cor": "Preto"
      }
    },
    {
      "product_id": 88,
      "name": "Giannini GF-1R Aço Folk Sunburst",
      "brand": "Giannini",
      "category": "Violões",
      "availability": "disponível",
      "available_for_sa
… (truncado)
```

</details>

---

**🙂 Cliente:**

Sou iniciante e quero tocar MPB. Qual desses você indica?

**🎸 Lia:**

Pra MPB, eu recomendo um violão com **cordas de nylon** — o som é mais morno e elegante, perfeito pro estilo.

Como você é iniciante, minha sugestão é:

**Yamaha C40** — R$ 599,90 (R$ 569,91 no PIX)

Por quê? A Yamaha é marca confiável, o C40 é feito pra estudantes e tem excelente projeção sonora. Você vai conseguir um som legal sem gastar muito. É o ponto de equilíbrio entre qualidade e preço.

Se quiser economizar um pouco, o **Tagima Memphis AC-39** (R$ 429,90) também é bom pra começar — é mais básico, mas funciona bem.

E se você tiver um orçamento um pouco maior e quiser algo com mais corpo sonoro, o **Giannini GN-15** (R$ 689,00) tem um som mais quente e encorpado, ótimo pra MPB também.

Qual desses te atrai? Quer saber mais detalhes de algum?

---

**🙂 Cliente:**

Em quantas vezes sem juros posso pagar o Yamaha C40?

**🎸 Lia:**

Perfeito! O Yamaha C40 pode ser parcelado em **até 6 vezes sem juros** no cartão de crédito:

- **1x** de R$ 599,90
- **2x** de R$ 299,95
- **3x** de R$ 199,97
- **4x** de R$ 149,98
- **5x** de R$ 119,98
- **6x** de R$ 99,98

Ou se preferir pagar à vista, tem **5% de desconto no PIX** — sai por **R$ 569,91**.

Quer prosseguir com a compra ou tem mais alguma dúvida?

<details><summary>🔧 Ferramentas chamadas: `payment_options`</summary>

**`payment_options`**

```json
{"product_ids": [81]}
```

Resultado:

```json
{
  "total": "R$ 599,90",
  "pix": "R$ 569,91",
  "pix_savings": "R$ 29,99",
  "pix_note": "5% de desconto no pagamento à vista via PIX.",
  "debit": "R$ 599,90 à vista (todas as bandeiras)",
  "boleto": "R$ 599,90 à vista; compensação em até 3 dias úteis",
  "credit_max_installments": 6,
  "credit_options": [
    "1x de R$ 599,90 sem juros",
    "2x de R$ 299,95 sem juros",
    "3x de R$ 199,97 sem juros",
    "4x de R$ 149,98 sem juros",
    "5x de R$ 119,98 sem juros",
    "6x de R$ 99,98 sem juros"
  ],
  "split_payment_allowed": false,
  "notes": []
}
```

</details>
