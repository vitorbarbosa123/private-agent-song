# Interfaces: web, terminal e API

[← Voltar ao README](../README.md)

## Interface web

`docker compose up` (ou `uv run streamlit run src/emporio/ui/app.py`) abre a interface em
http://localhost:8501. Ela segue o modelo dos chats de IA atuais:

- **Conversas na barra lateral,** com título (a primeira pergunta). Dá para criar uma nova,
  retomar qualquer conversa anterior e apagar a atual (direito de exclusão, LGPD).
- **Histórico persistente** no mesmo SQLite usado pelo terminal.
- **Ferramentas chamadas em cada resposta:** um painel expansível mostra quais ferramentas a
  assistente usou, com os parâmetros enviados e o resultado recebido. Facilita entender e
  auditar as decisões do agente. Pode ser desligado na barra lateral.
- **Sugestões iniciais** com as quatro perguntas do enunciado.
- **Simulação de data e hora,** útil porque os pedidos da base são de 2025-2026 (ex.: testar o
  prazo de devolução ou a loja fechada no domingo).
- **Página "Atendimentos":** a equipe vê e encerra os casos encaminhados pela assistente.

A interface foi testada de ponta a ponta com o `AppTest` do Streamlit dentro do container:
clique em uma sugestão, resposta real do modelo, painel de ferramentas, conversa na barra lateral
e um segundo turno usando o contexto ("e em quantas vezes posso pagar *ele*?").

## Conversando pelo terminal

```bash
uv run emporio-chat                          # conversa interativa
uv run emporio-chat --debug                  # mostra as ferramentas chamadas e seus resultados
uv run emporio-chat --now 2026-03-02T10:30   # simula data/hora (os pedidos da base são de 2025-2026)
uv run emporio-chat --model openai/gpt-4o-mini            # testa outro modelo sem editar o .env
uv run emporio-chat -m "Oi" -m "Quanto custa o Takamine GD20?"  # roteiro não interativo
uv run emporio-chat --sessions               # lista conversas salvas
uv run emporio-chat --session <id>           # retoma uma conversa (o id aparece ao sair)
uv run emporio-chat --no-persist             # não grava histórico nem atendimentos
uv run emporio-handoffs [--all] [--close N]  # equipe: lista e encerra atendimentos encaminhados
```

Durante a conversa: `/novo` inicia outra conversa, `/esquecer` apaga o histórico da conversa
atual, `/debug` liga e desliga os detalhes, `/sair` encerra.

Dados de teste para consultar pedidos (fictícios, de `data/`): pedido **8** com o e-mail
`anacarol.ferreira@coldmail.com` (enviado, com rastreio) ou pedido **7** com
`leticia.rocha@jmail.com` (entregue). Com `--now 2026-02-20T10:00`, o pedido 7 ainda está
dentro do prazo de arrependimento.

## API REST

`docker compose up` também sobe uma API (FastAPI) em http://localhost:8710, com documentação
interativa em `/docs`. Ela é a porta de integração com canais reais (WhatsApp Business, site, CRM)
e usa as mesmas conversas e atendimentos da interface web e do terminal.

| Endpoint | Função |
|---|---|
| `POST /conversations` | Cria uma conversa |
| `GET /conversations` | Lista conversas (com título) |
| `POST /conversations/{id}/messages` | Envia a mensagem do cliente e devolve a resposta; `?include_tools=true` inclui as ferramentas chamadas |
| `GET /conversations/{id}` | Histórico em turnos |
| `DELETE /conversations/{id}` | Apaga a conversa (LGPD) |
| `GET /handoffs`, `POST /handoffs/{id}/close` | Atendimentos encaminhados para a equipe |
| `GET /health` | Healthcheck (público) |

```bash
curl -s -X POST localhost:8710/conversations/minha-conversa/messages \
  -H 'Content-Type: application/json' -d '{"message": "Quanto custa o Takamine GD20?"}'
```

Com `EMPORIO_API_KEY` definida, todas as rotas (exceto `/health`) exigem o cabeçalho
`X-API-Key`. No Compose a porta fica ligada só ao `localhost` e é configurável
(`EMPORIO_API_PORT`). Falhas do provedor não viram erro HTTP: a resposta traz a mensagem de
fallback com `"error": true`, para o canal decidir o que fazer.
