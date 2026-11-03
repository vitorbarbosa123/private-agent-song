"""Registro de atendimentos encaminhados para a equipe humana (handoff).

O manual (7.3) manda "registrar a reclamação e encaminhar para o responsável", com retorno
em até 24 horas úteis. O agente registra o caso aqui, com um resumo para que a equipe não
precise reler a conversa, e devolve um protocolo ao cliente.

A equipe consulta e encerra os atendimentos com `uv run emporio-handoffs`.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from emporio.business_hours import STORE_TZ

_SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    summary TEXT NOT NULL,
    customer_name TEXT,
    contact TEXT,
    order_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    closed_at TEXT
)
"""


@dataclass(frozen=True)
class Ticket:
    id: int
    created_at: datetime
    session_id: str
    reason: str
    summary: str
    customer_name: str | None
    contact: str | None
    order_id: int | None
    status: str

    @property
    def code(self) -> str:
        return f"ATD-{self.id:05d}"


class HandoffStore:
    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)

    def create(
        self,
        *,
        session_id: str,
        reason: str,
        summary: str,
        customer_name: str | None = None,
        contact: str | None = None,
        order_id: int | None = None,
        now: datetime | None = None,
    ) -> Ticket:
        created = (now or datetime.now(STORE_TZ)).isoformat(timespec="seconds")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO handoffs (created_at, session_id, reason, summary, customer_name, contact, order_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (created, session_id, reason, summary, customer_name, contact, order_id),
            )
        return self.get(cursor.lastrowid)  # type: ignore[return-value]

    def get(self, ticket_id: int) -> Ticket | None:
        row = self._conn.execute("SELECT * FROM handoffs WHERE id = ?", (ticket_id,)).fetchone()
        return _to_ticket(row) if row else None

    def find_open(self, session_id: str, reason: str) -> Ticket | None:
        row = self._conn.execute(
            "SELECT * FROM handoffs WHERE session_id = ? AND reason = ? AND status = 'open' ORDER BY id DESC",
            (session_id, reason),
        ).fetchone()
        return _to_ticket(row) if row else None

    def list(self, *, include_closed: bool = False) -> list[Ticket]:
        query = "SELECT * FROM handoffs" + ("" if include_closed else " WHERE status = 'open'") + " ORDER BY id"
        return [_to_ticket(r) for r in self._conn.execute(query).fetchall()]

    def close(self, ticket_id: int, now: datetime | None = None) -> bool:
        closed = (now or datetime.now(STORE_TZ)).isoformat(timespec="seconds")
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE handoffs SET status = 'closed', closed_at = ? WHERE id = ? AND status = 'open'",
                (closed, ticket_id),
            )
        return cursor.rowcount == 1


def _to_ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        session_id=row["session_id"],
        reason=row["reason"],
        summary=row["summary"],
        customer_name=row["customer_name"],
        contact=row["contact"],
        order_id=row["order_id"],
        status=row["status"],
    )


def main(argv: list[str] | None = None) -> None:
    """Painel mínimo para a equipe: lista e encerra atendimentos encaminhados."""
    from rich.console import Console
    from rich.table import Table

    from emporio.config import get_settings

    parser = argparse.ArgumentParser(description="Atendimentos encaminhados pela assistente virtual.")
    parser.add_argument("--all", action="store_true", help="Inclui atendimentos encerrados.")
    parser.add_argument("--close", type=int, metavar="ID", help="Encerra o atendimento (número sem 'ATD-').")
    args = parser.parse_args(argv)

    store = HandoffStore(get_settings().handoffs_path)
    console = Console()
    if args.close is not None:
        ok = store.close(args.close)
        console.print(f"ATD-{args.close:05d} encerrado." if ok else f"ATD-{args.close:05d} não está aberto.")
        return

    tickets = store.list(include_closed=args.all)
    if not tickets:
        console.print("Nenhum atendimento " + ("registrado." if args.all else "aberto."))
        return
    table = Table(title="Atendimentos encaminhados")
    for column in ("Protocolo", "Aberto em", "Motivo", "Cliente", "Contato", "Pedido", "Resumo", "Status"):
        table.add_column(column, overflow="fold")
    for t in tickets:
        table.add_row(t.code, f"{t.created_at:%d/%m %H:%M}", t.reason, t.customer_name or "-",
                      t.contact or "-", str(t.order_id or "-"), t.summary, t.status)
    console.print(table)


if __name__ == "__main__":
    main()
