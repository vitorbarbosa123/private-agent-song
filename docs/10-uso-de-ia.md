# Uso de assistentes de código

[← Voltar ao README](../README.md)

Usei o **Claude Code** (Anthropic), dentro do VS Code, como par de programação durante todo o
projeto. A divisão de papéis foi: **eu decidi o que construir e aprovei cada etapa; o assistente
propôs, implementou, testou e explicou**. O histórico de commits, um por objetivo e fase, reflete
esse fluxo.

## Como foi o fluxo

1. **Análise e segurança dos arquivos.** Antes de qualquer código, pedi uma análise do enunciado
   e dos dados, incluindo uma varredura por conteúdo malicioso ou prompts escondidos (JavaScript
   e ações automáticas nos PDFs, texto invisível, caracteres Unicode ocultos, tentativas de
   prompt injection nos CSVs). Nada foi encontrado.
2. **Plano em fases.** O assistente propôs uma arquitetura e um plano de implementação (dados →
   ferramentas → RAG → agente → memória → guardrails → avaliação → interfaces), e eu ajustei as
   escolhas antes de cada fase.
3. **Decisões que tomei e que mudaram o rumo do projeto:**
   - usar o **OpenRouter** com um *preset*, para configurar modelo e fallbacks pela plataforma e
     deixar a troca de modelo a cargo de quem avalia;
   - rodar tudo em **containers** e ter uma **interface de chat** com histórico e inspeção das
     ferramentas;
   - usar o **Langfuse** para observabilidade;
   - manter a política de retenção zero de dados (ZDR) no OpenRouter, o que levou à troca do
     modelo do preset para um que tivesse endpoint compatível com ferramentas.
4. **Implementação com testes.** Cada fase foi implementada pelo assistente com testes
   automatizados (mais de 300, sem chamadas ao modelo) e revisada por mim antes do commit.
5. **Testes ao vivo e avaliação como fonte de correções.** Boa parte das melhorias veio de rodar
   o agente de verdade e ler as respostas: protocolo de atendimento inventado pelo modelo,
   correção interna vazando para o cliente, aviso de cartão ignorado, número do cartão
   aparecendo nos rastreamentos do Langfuse, avaliador LLM reprovando respostas corretas.
   Cada caso virou uma correção na causa e um teste de regressão, e está documentado nas
   respectivas seções.
6. **Testes manuais meus.** Simulações feitas por mim também geraram correções, como a
   reclamação de defeito com um número de pedido inexistente, que antes não oferecia o
   atendimento humano.

## O que funcionou bem e o que exigiu atenção

- **Funcionou bem:** velocidade para implementar e testar alternativas (por exemplo, comparar
  estratégias de RAG e modelos com números), e disciplina de documentar cada decisão.
- **Exigiu atenção:** o assistente também erra (valores esperados errados em testes, falhas de
  configuração, verificações rígidas demais na avaliação). A revisão das saídas reais e os
  conjuntos de validação separados foram o que pegou esses erros. Também foi preciso cuidado
  para não ajustar o agente até "passar" nos mesmos cenários usados para medi-lo.
