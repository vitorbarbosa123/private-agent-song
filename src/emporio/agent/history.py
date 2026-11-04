"""Reconstrói o histórico salvo de uma conversa em turnos legíveis.

O checkpointer guarda a sequência bruta de mensagens (cliente, chamadas de ferramenta,
resultados, resposta). Interfaces (Streamlit, CLI) precisam de "turnos": o que o cliente
disse, o que a assistente respondeu e quais ferramentas foram usadas no meio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from emporio.agent.graph import ToolCallRecord, message_text


@dataclass
class ChatTurn:
    user: str
    reply: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


def conversation_turns(messages: list[AnyMessage]) -> list[ChatTurn]:
    turns: list[ChatTurn] = []
    outputs: dict[str, str] = {}
    for message in messages:
        if isinstance(message, HumanMessage):
            turns.append(ChatTurn(user=str(message.content)))
        elif not turns:
            continue
        elif isinstance(message, ToolMessage):
            outputs[message.tool_call_id] = str(message.content)
        elif isinstance(message, AIMessage):
            for call in message.tool_calls:
                turns[-1].tool_calls.append(ToolCallRecord(call["name"], call["args"], call["id"]))
            if text := message_text(message):
                turns[-1].reply = text
    # Os resultados chegam depois das chamadas: preenche usando o id da chamada.
    for turn in turns:
        turn.tool_calls = [ToolCallRecord(c.name, c.args, outputs.get(c.output, "")) for c in turn.tool_calls]
    return turns
