"""Interface de terminal para conversar com o agente.

Uso:
    uv run emporio-chat                         # conversa interativa
    uv run emporio-chat --debug                 # mostra as ferramentas chamadas
    uv run emporio-chat --now 2026-03-02T10:30  # fixa a data/hora vista pelo agente
    uv run emporio-chat --model openai/gpt-4o-mini
    uv run emporio-chat -m "Oi" -m "Quanto custa o Takamine GD20?"   # roteiro, sem interação
    uv run emporio-chat --sessions              # lista conversas salvas
    uv run emporio-chat --session <id>          # retoma uma conversa
    uv run emporio-chat --no-persist            # não grava histórico nem atendimentos

Comandos durante a conversa: /novo (nova conversa), /esquecer (apaga esta conversa),
/debug (liga/desliga detalhes), /sair.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from langchain_core.messages import AIMessage, HumanMessage
from rich.prompt import Prompt

from emporio.agent import AgentReply, ChatSession, EmporioAgent, create_agent
from emporio.agent.graph import message_text
from emporio.agent.memory import list_sessions
from emporio.agent.prompts import ASSISTANT_NAME
from emporio.config import get_settings
from emporio.llm import LLMConfigError, resolve_model

console = Console()
HELP = "[dim]Comandos: /novo · /esquecer · /debug · /sair[/dim]"


def show_reply(reply: AgentReply, debug: bool) -> None:
    if debug:
        for call in reply.tool_calls:
            args = json.dumps(call.args, ensure_ascii=False)
            output = call.output if len(call.output) <= 400 else call.output[:400] + "…"
            console.print(f"[dim]🔧 {call.name}({args})\n   → {output}[/dim]")
    style = "red" if reply.error else "magenta"
    console.print(Panel(Markdown(reply.text), title=ASSISTANT_NAME, title_align="left", border_style=style))


def ask(session: ChatSession, message: str, debug: bool) -> None:
    with console.status(f"{ASSISTANT_NAME} está digitando…", spinner="dots"):
        reply = session.send(message)
    show_reply(reply, debug)


def show_recent(session: ChatSession, exchanges: int = 2) -> None:
    """Ao retomar uma conversa, mostra as últimas trocas para dar contexto."""
    visible = [m for m in session.history()
               if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and message_text(m))]
    for message in visible[-2 * exchanges:]:
        who = "Você" if isinstance(message, HumanMessage) else ASSISTANT_NAME
        text = message.content if isinstance(message, HumanMessage) else message_text(message)
        plain = text.replace("**", "").replace("\n\n", " ").replace("\n", " ")
        console.print(f"[dim]{who}: {plain[:300]}[/dim]", markup=False, highlight=False)


def goodbye(session: ChatSession, persistent: bool) -> None:
    console.print("[dim]Até logo! 🎶[/dim]")
    if persistent and session.history():
        console.print(f"[dim]Para retomar esta conversa: uv run emporio-chat --session {session.thread_id}[/dim]")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Converse com a assistente da Empório da Música.")
    parser.add_argument("--debug", action="store_true", help="Mostra as chamadas de ferramentas.")
    parser.add_argument("--now", type=datetime.fromisoformat, help="Data/hora simulada (AAAA-MM-DDTHH:MM).")
    parser.add_argument("--model", help="Sobrescreve LLM_MODEL (ex.: openai/gpt-4o-mini).")
    parser.add_argument("-m", "--message", action="append", help="Envia mensagens em sequência e sai.")
    parser.add_argument("--session", help="Retoma uma conversa salva.")
    parser.add_argument("--sessions", action="store_true", help="Lista as conversas salvas e sai.")
    parser.add_argument("--no-persist", action="store_true", help="Não grava histórico nem atendimentos.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
    if args.debug:
        logging.getLogger("emporio").setLevel(logging.DEBUG)

    settings = get_settings()
    overrides = {k: v for k, v in {"emporio_now": args.now, "llm_model": args.model}.items() if v}
    if overrides:
        settings = settings.model_copy(update=overrides)

    persistent = not args.no_persist
    try:
        agent: EmporioAgent = create_agent(settings, persistent=persistent)
    except LLMConfigError as exc:
        raise SystemExit(f"Erro de configuração: {exc}") from exc

    if args.sessions:
        sessions = list_sessions(agent.checkpointer)
        if not sessions:
            console.print("Nenhuma conversa salva.")
        for info in sessions:
            console.print(f"{info.thread_id}  [dim]{info.updated_at:%d/%m/%Y %H:%M} · {info.messages} mensagens[/dim]")
        return

    session = agent.new_session(args.session)

    now = agent.clock()
    console.print(Panel.fit(
        f"[bold]Empório da Música[/bold] · atendimento virtual\n"
        f"[dim]Modelo: {resolve_model(settings)} · Agora: {now:%d/%m/%Y %H:%M}[/dim]",
        border_style="magenta",
    ))
    if args.session:
        if session.history():
            console.print("[dim]Retomando a conversa:[/dim]")
            show_recent(session)
        else:
            console.print(f"[yellow]Conversa {args.session} não encontrada; iniciando uma nova com esse id.[/yellow]")

    if args.message:
        for message in args.message:
            console.print(f"[bold cyan]Você:[/bold cyan] {escape(message)}")
            ask(session, message, args.debug)
        return

    console.print(HELP)
    debug = args.debug
    while True:
        try:
            message = Prompt.ask("[bold cyan]Você[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            goodbye(session, persistent)
            return
        if not message:
            continue
        command = message.lower()
        if command in {"/sair", "/exit", "/quit"}:
            goodbye(session, persistent)
            return
        if command == "/novo":
            session = agent.new_session()
            console.print("[dim]Nova conversa iniciada.[/dim]")
            continue
        if command == "/esquecer":
            session.forget()
            session = agent.new_session()
            console.print("[dim]Histórico desta conversa apagado. Nova conversa iniciada.[/dim]")
            continue
        if command == "/debug":
            debug = not debug
            console.print(f"[dim]Modo debug {'ligado' if debug else 'desligado'}.[/dim]")
            continue
        if command.startswith("/"):
            console.print(HELP)
            continue
        ask(session, message, debug)


if __name__ == "__main__":
    main()
