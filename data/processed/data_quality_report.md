# Relatório de qualidade dos dados

Gerado automaticamente por `uv run emporio-clean-data`. Não edite à mão.

Princípio adotado: **sinalizar em vez de corrigir silenciosamente**. Valores só são alterados quando a correção é inequívoca; nos demais casos o dado original é mantido e o problema fica exposto em colunas derivadas e neste relatório.

## Resumo

| Tabela | Registros tratados | info | warning | error |
|---|---:|---:|---:|---:|
| categories | 9 | 0 | 3 | 0 |
| products | 65 | 3 | 9 | 0 |
| promotions | 25 | 3 | 0 | 0 |
| customers | 50 | 3 | 1 | 0 |
| orders | 20 | 0 | 5 | 0 |
| order_items | 22 | 0 | 2 | 0 |
| policies (seções) | 29 | 0 | 2 | 0 |

## Problemas por regra

### `products` · `name_typo` (info, 1)

| Registro | Problema | Ação |
|---|---|---|
| 84 | Erro de digitação no nome: 'Giannini GN-15 Nylon Cedr Natural'. | Nome corrigido para 'Giannini GN-15 Nylon Cedro Natural'. |

### `products` · `out_of_stock` (info, 1)

| Registro | Problema | Ação |
|---|---|---|
| 96 | 'Giannini GF-3D Dreadnought Sunburst' está ativo, porém esgotado. | is_sellable=False; o agente deve sugerir alternativas (seção 7.3). |

### `products` · `coming_soon_with_stock` (warning, 1)

| Registro | Problema | Ação |
|---|---|---|
| 130 | 'Kala KA-ABP-CTG Barítono Cedar' está como 'coming_soon' mas tem 2 unidade(s) em estoque. | Tratado como indisponível para venda até a mudança de status. |

### `products` · `description_conflict` (warning, 7)

| Registro | Problema | Ação |
|---|---|---|
| 135 | 'Music Man Bass 1X Electric Bass': descrição cita Fender, mas o produto é Music Man. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 136 | 'Ibanez Bass 2X Electric Bass': descrição cita Fender, mas o produto é Ibanez. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 137 | 'Yamaha Bass 3X Electric Bass': descrição cita Ibanez, mas o produto é Yamaha; descrição cita 5 cordas, specs indicam 4. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 139 | 'Bateria Acústica Yamaha Kit 1 Studio': descrição cita Pearl, mas o produto é Yamaha. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 140 | 'Bateria Acústica Pearl Kit 2 Studio': descrição cita Tama, mas o produto é Pearl. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 142 | 'Teclado Sintetizador Korg Synth 1 Pro': descrição cita Roland, mas o produto é Korg; descrição cita 88 teclas, specs indicam 61. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |
| 144 | 'Teclado Sintetizador Roland Synth 3 Pro': descrição cita Yamaha, mas o produto é Roland. | Descrição original preservada em 'description_original'; 'description' substituída por texto gerado a partir de nome + specs; description_verified=False. |

### `products` · `discontinued_with_stock` (warning, 1)

| Registro | Problema | Ação |
|---|---|---|
| 136 | 'Ibanez Bass 2X Electric Bass' está descontinuado mas tem 13 unidade(s) em estoque. | Tratado como indisponível (seção 7.3: produto descontinuado). Estoque residual a confirmar com a equipe. |

### `products` · `ambiguous_specs_strings` (info, 1)

| Registro | Problema | Ação |
|---|---|---|
|  | O campo specs.strings indica o tipo de corda nos violões/ukuleles ('nylon', 'steel') e a quantidade de cordas nas guitarras/baixos ('4', '6'). | Separado em specs.string_type ('nylon'/'aço') e specs.string_count (inteiro). |

### `promotions` · `multiple_promotions_history` (info, 3)

| Registro | Problema | Ação |
|---|---|---|
| 6, 23 | Produto 93 possui 2 promoções cadastradas (0 ativa). | Apenas promoções ativas são consideradas no preço vigente. |
| 8, 22 | Produto 96 possui 2 promoções cadastradas (0 ativa). | Apenas promoções ativas são consideradas no preço vigente. |
| 9, 25 | Produto 99 possui 2 promoções cadastradas (0 ativa). | Apenas promoções ativas são consideradas no preço vigente. |

### `categories` · `empty_category` (warning, 3)

| Registro | Problema | Ação |
|---|---|---|
| 6 | Categoria 'Instrumentos de Sopro (Madeiras)' não possui nenhum produto cadastrado, embora o manual cite essa linha de instrumentos. | Mantida. O agente deve informar que não há itens disponíveis no momento. |
| 7 | Categoria 'Instrumentos de Sopro (Metais)' não possui nenhum produto cadastrado, embora o manual cite essa linha de instrumentos. | Mantida. O agente deve informar que não há itens disponíveis no momento. |
| 8 | Categoria 'Cordas Orquestrais' não possui nenhum produto cadastrado, embora o manual cite essa linha de instrumentos. | Mantida. O agente deve informar que não há itens disponíveis no momento. |

### `customers` · `shared_email` (warning, 1)

| Registro | Problema | Ação |
|---|---|---|
| 11, 43 | Clientes distintos (Bruno Carvalho Martins / Bruno Martins) compartilham o mesmo e-mail: bruno.martins@jmail.com. | Cadastros mantidos (não há base para fundi-los). O e-mail sozinho não identifica o cliente: a autenticação exige número do pedido + e-mail/telefone. |

### `customers` · `possible_duplicate_customer` (info, 3)

| Registro | Problema | Ação |
|---|---|---|
| 11, 27 | Nomes possivelmente da mesma pessoa: 'Bruno Carvalho Martins' e 'Bruno Carvalho'. | Nenhuma fusão automática; apenas sinalizado para revisão humana. |
| 11, 43 | Nomes possivelmente da mesma pessoa: 'Bruno Carvalho Martins' e 'Bruno Martins'. | Nenhuma fusão automática; apenas sinalizado para revisão humana. |
| 13, 47 | Nomes possivelmente da mesma pessoa: 'Diego Fernandes Castro' e 'Diego Castro'. | Nenhuma fusão automática; apenas sinalizado para revisão humana. |

### `orders` · `installment_policy_violation` (warning, 3)

| Registro | Problema | Ação |
|---|---|---|
| 9 | Parcelamento em 6x de R$ 58,32 viola a política vigente (seção 3.1: mínimo de R$ 80,00 por parcela). | Mantido (registro histórico); installment_plan_valid=False. O agente não deve usar esse pedido como referência de condição de pagamento. |
| 16 | Parcelamento em 6x de R$ 71,65 viola a política vigente (seção 3.1: mínimo de R$ 80,00 por parcela). | Mantido (registro histórico); installment_plan_valid=False. O agente não deve usar esse pedido como referência de condição de pagamento. |
| 18 | Parcelamento em 12x de R$ 38,32 viola a política vigente (seção 3.1: mínimo de R$ 100,00 por parcela). | Mantido (registro histórico); installment_plan_valid=False. O agente não deve usar esse pedido como referência de condição de pagamento. |

### `orders` · `total_mismatch` (warning, 2)

| Registro | Problema | Ação |
|---|---|---|
| 3 | Total registrado R$ 3.450,00 difere da soma dos itens a preço de catálogo atual R$ 3.498,00 (diferença de R$ 48,00 a menos). | Mantido o total registrado (valor efetivamente cobrado). Diferença exposta em 'total_divergence_brl'; o agente informa o total registrado. |
| 20 | Total registrado R$ 1.400,00 difere da soma dos itens a preço de catálogo atual R$ 1.488,00 (diferença de R$ 88,00 a menos). | Mantido o total registrado (valor efetivamente cobrado). Diferença exposta em 'total_divergence_brl'; o agente informa o total registrado. |

### `order_items` · `coming_soon_product_sold` (warning, 2)

| Registro | Problema | Ação |
|---|---|---|
| 3/130 | Pedido 3 (delivered) contém 'Kala KA-ABP-CTG Barítono Cedar', que está cadastrado como 'coming_soon' (ainda não lançado). | Mantido; indica status de produto desatualizado no cadastro. |
| 14/130 | Pedido 14 (pending) contém 'Kala KA-ABP-CTG Barítono Cedar', que está cadastrado como 'coming_soon' (ainda não lançado). | Mantido; indica status de produto desatualizado no cadastro. |

### `policies` · `conflicting_phones` (warning, 1)

| Registro | Problema | Ação |
|---|---|---|
|  | O manual cita telefones diferentes para a loja: (67)3321-4500, (67)3341-4444. | Adotado (67) 3341-4444 como canônico (ver resolução 'Telefone / WhatsApp'). |

### `policies` · `conflicting_emails` (warning, 1)

| Registro | Problema | Ação |
|---|---|---|
|  | O manual cita grafias diferentes de e-mail: contato@emporiodamusica.com.br, contato@empóriodamusica.com.br. | Adotado contato@emporiodamusica.com.br como canônico (ver resolução 'E-mail'). |

## Interpretações adotadas para o manual de políticas

- **Telefone / WhatsApp** (seção Capa, 1.2 e 7): Número canônico: (67) 3341-4444. O agente não informa o (67) 3321-4500. _Motivo:_ Aparece duas vezes, inclusive na tabela de dados cadastrais da empresa, que é a fonte mais 'oficial' do documento. Divergência a confirmar com a loja.
- **E-mail** (seção Capa e 1.2): E-mail canônico sem acento: contato@emporiodamusica.com.br. _Motivo:_ Domínios com acento (IDN) são raros e propensos a erro de digitação; a versão com acento é quase certamente um erro de autocorreção.
- **Parcela mínima no cartão de crédito** (seção 3 e 3.1): Vale a seção 3.1 (faixas). A tabela descreve apenas o caso de 12x. _Motivo:_ Regra específica prevalece sobre a geral; aplicar R$ 100 a todos os parcelamentos tornaria a seção 3.1 sem efeito.
- **Parcelamento em até 3x** (seção 3.1): Em 2x ou 3x cada parcela deve ser de no mínimo R$ 50,00. 1x é sempre permitido. _Motivo:_ Interpretação que dá sentido à exceção e mantém a progressão das faixas (50 → 80 → 100).
- **Frete grátis na região metropolitana** (seção 5.1): Pedidos de R$ 500,00 ou mais têm frete grátis. _Motivo:_ Interpretação mais favorável ao consumidor (art. 47 do CDC).
- **Região metropolitana de Campo Grande** (seção 5.1): Entrega por motoboy (regra de R$ 500/R$ 35) só para Campo Grande. Demais cidades: Correios/Jadlog, com valor calculado no checkout. _Motivo:_ Os clientes da base estão em Campo Grande ou em cidades a mais de 200 km (Dourados, Três Lagoas, Corumbá, Ponta Porã). Prometer motoboy para outro município sem confirmação seria arriscado.
- **Data de recebimento do pedido** (seção 4.1 e 8.1): Usa a data informada pelo cliente; na falta dela, a previsão de entrega. A resposta deixa claro qual data foi usada. _Motivo:_ É a melhor aproximação disponível e é transparente com o cliente.
- **Troca por defeito vs. garantia legal** (seção 4.2 e 8.1): São regras complementares: até 30 dias da compra → troca direta na loja; até 90 dias do recebimento → garantia legal (a loja intermedia); depois → garantia do fabricante. Casos de defeito são sempre encaminhados a um atendente humano. _Motivo:_ Pelo CDC a loja responde solidariamente durante a garantia legal; o agente não deve negar atendimento entre o 31º e o 90º dia.
- **Direito de arrependimento: canal da compra** (seção 4.1): Todos os pedidos da base são tratados como compras online (possuem fluxo de envio/entrega). _Motivo:_ A base só registra pedidos com entrega; compras no balcão não aparecem nela.
- **Tamanho do catálogo** (seção 1): O agente responde apenas com base no catálogo do sistema e, para categorias sem produtos, informa que não há itens disponíveis no momento e oferece contato humano. _Motivo:_ Seção 7.1: nunca informar preço ou estoque sem consultar o sistema.
