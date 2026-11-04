# Limitações conhecidas

[← Voltar ao README](../README.md)

- **Guardrails baseados em padrões.** A detecção de manipulação usa expressões regulares em
  português e inglês. Ataques mais elaborados (instruções escondidas, outros idiomas, paráfrases)
  podem passar; nesse caso, o que segura é a regra do prompt e as verificações de saída. A
  verificação de preços só cobre valores escritos com "R$".

- **Limite de tentativas de verificação por processo.** O contador de tentativas erradas de
  identificação é por conversa, mas fica em memória: se a conversa for retomada em outro
  processo, ele recomeça. Numa API real, ficaria no estado persistido da conversa.

- **Validação de marcas por dicionário.** A detecção de descrições conflitantes usa uma lista de
  marcas e modelos conhecidos. Uma marca nova no catálogo precisa ser adicionada a `BRANDS` em
  `products.py`.
- **Busca textual por regras.** Sinônimos ("acústico" vs. "folk", "elétrico" vs.
  "eletroacústico") não são tratados. Com um catálogo maior, valeria uma busca híbrida (BM25 +
  embeddings).
- **Data real de entrega.** A base só tem a previsão de entrega; os prazos de devolução usam a
  data informada pelo cliente ou essa previsão.
- **Feriados municipais de outras cidades e pontos facultativos** (Carnaval, Corpus Christi) não
  são considerados no horário da loja.
- **Conjuntos de avaliação pequenos** (28 + 22 perguntas, escritas por mim). Servem para comparar
  estratégias e pegar regressões, mas as diferenças de poucos pontos percentuais não são
  estatisticamente robustas. Com mais tempo, coletaria perguntas reais do WhatsApp da loja.
- **Promoções sem datas.** Sem datas de vigência, `is_active` é a única fonte de verdade.
- **Divergências não resolvidas na origem.** Telefone, status do produto 130 e totais dos pedidos
  3 e 20 precisariam ser confirmados com a loja. Com mais tempo, o relatório de qualidade viraria
  uma fila de revisão para a equipe.

## O que eu faria com mais tempo

- **Avaliação mais robusta:** rodar cada cenário várias vezes e reportar taxas de aprovação,
  criar um conjunto de cenários separado só para validação do agente e usar perguntas reais
  de clientes (por exemplo, do WhatsApp da loja).
- **Concluir a comparação de modelos:** checar o Gemini 2.5 Flash com um avaliador de outra
  família e incluir modelos maiores (Claude Sonnet). Se a vantagem do Flash se confirmar,
  trocar o modelo do preset, sem mudar código.
- **Medir o cache de prompt** (tokens lidos do cache e economia por conversa).
- **Integração com canais reais:** conectar a API ao WhatsApp Business e o encaminhamento ao
  CRM ou à ferramenta de atendimento da loja.
- **Revisão humana dos dados:** transformar o relatório de qualidade numa fila de pendências
  para a equipe confirmar (telefone divergente, status de produtos, totais de pedidos).
- **Estado persistido completo:** guardar no histórico da conversa o limite de tentativas de
  verificação de identidade.
- **Busca de produtos semântica,** caso o catálogo cresça muito além dos 65 itens atuais.

