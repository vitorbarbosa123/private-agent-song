"""Histórico persistente das conversas (checkpointer SQLite do LangGraph).

Cada conversa é uma `thread_id`: o cliente pode fechar o terminal e retomar depois com
`emporio-chat --session <id>`. O histórico contém dados pessoais (nome, e-mail, telefone
informados na conversa), por isso:
- fica fora do repositório (`var/`, no .gitignore);
- pode ser apagado a pedido do cliente (`/esquecer` no chat), como prevê a seção 9 do
  manual (LGPD). Os atendimentos já encaminhados à equipe são registros separados.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from emporio.business_hours import STORE_TZ


def open_checkpointer(path: Path) -> SqliteSaver:
    path.parent.mkdir(parents=True, exist_ok=True)
    saver = SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))
    saver.setup()
    return saver


@dataclass(frozen=True)
class SessionInfo:
    thread_id: str
    updated_at: datetime
    messages: int
    title: str = ""  # primeira mensagem do cliente, para listar conversas


def _title(messages: list) -> str:
    first = next((m for m in messages if getattr(m, "type", "") == "human"), None)
    text = " ".join(str(first.content).split()) if first else ""
    return text if len(text) <= 48 else text[:47] + "…"


def list_sessions(saver: BaseCheckpointSaver, limit: int = 20) -> list[SessionInfo]:
    """Conversas salvas, da mais recente para a mais antiga."""
    latest: dict[str, SessionInfo] = {}
    for item in saver.list(None):
        thread_id = item.config["configurable"]["thread_id"]
        updated = datetime.fromisoformat(item.checkpoint["ts"]).astimezone(STORE_TZ)
        if thread_id in latest and latest[thread_id].updated_at >= updated:
            continue
        messages = item.checkpoint["channel_values"].get("messages", [])
        if not messages:
            continue
        latest[thread_id] = SessionInfo(thread_id, updated, len(messages), _title(messages))
    return sorted(latest.values(), key=lambda s: s.updated_at, reverse=True)[:limit]
