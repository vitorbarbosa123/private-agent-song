"""Gera as conversas de exemplo em `examples/` a partir de conversas reais com o agente.

Uso:
    uv run emporio-export-examples                # todas as conversas do roteiro
    uv run emporio-export-examples --only 03      # só as que contêm "03" no id

O roteiro (mensagens do cliente e data simulada) fica em `evals/example_conversations.yaml`;
as respostas e as ferramentas chamadas são as do agente real no momento da execução. Assim
os exemplos são reproduzíveis e nunca escritos à mão.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from emporio.agent import AgentReply, EmporioAgent
from emporio.agent.graph import ToolCallRecord
from emporio.agent.prompts import ASSISTANT_NAME
from emporio.business_hours import STORE_TZ, WEEKDAY_NAMES
from emporio.config import get_settings
from emporio.data.paths import PROJECT_ROOT
from emporio.handoff import HandoffStore
from emporio.llm import resolve_model

SCRIPT = PROJECT_ROOT / "evals" / "example_conversations.yaml"
OUTPUT_DIR = PROJECT_ROOT / "examples"
MAX_TOOL_OUTPUT = 2500


class ExampleConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    highlights: str
    now: datetime
    turns: list[str]


def load_script(path: Path = SCRIPT) -> list[ExampleConversation]:
    return [ExampleConversation(**c) for c in yaml.safe_load(path.read_text(encoding="utf-8"))["conversations"]]


def _tool_block(calls: list[ToolCallRecord]) -> list[str]:
    if not calls:
        return []
    names = ", ".join(f"`{c.name}`" for c in calls)
    lines = ["", f"<details><summary>🔧 Ferramentas chamadas: {names}</summary>", ""]
    for call in calls:
        output = call.output
        try:
            output = json.dumps(json.loads(output), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            pass
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n… (truncado)"
        lines += [
            f"**`{call.name}`**", "",
            "```json", json.dumps(call.args, ensure_ascii=False), "```", "",
            "Resultado:", "", "```json", output, "```", "",
        ]
    lines += ["</details>"]
    return lines


def render_markdown(conv: ExampleConversation, replies: list[AgentReply], configured_model: str) -> str:
    now = conv.now
    served = sorted({r.model for r in replies if r.model})
    model = configured_model + (f" → {', '.join(served)}" if served and served != [configured_model] else "")
    cost = sum(r.cost_usd or 0 for r in replies)
    lines = [
        f"# {conv.title}",
        "",
        f"> **O que este exemplo mostra:** {conv.highlights}",
        ">",
        f"> Data simulada: {WEEKDAY_NAMES[now.weekday()]}, {now:%d/%m/%Y %H:%M} · Modelo: `{model}` · "
        f"Custo: US$ {cost:.4f}",
        ">",
        "> Gerado por `uv run emporio-export-examples` a partir de uma conversa real com o agente.",
        "",
    ]
    for message, reply in zip(conv.turns, replies, strict=True):
        lines += ["---", "", "**🙂 Cliente:**", "", message, "", f"**🎸 {ASSISTANT_NAME}:**", "", reply.text]
        lines += _tool_block(reply.tool_calls)
        lines.append("")
    return "\n".join(lines)


def render_index(items: list[tuple[ExampleConversation, Path]]) -> str:
    lines = [
        "# Conversas de exemplo",
        "",
        "Conversas reais com a assistente, geradas por `uv run emporio-export-examples` a partir do roteiro "
        "em [`evals/example_conversations.yaml`](../evals/example_conversations.yaml). Em cada resposta, "
        "o bloco \"Ferramentas chamadas\" mostra o que a assistente consultou.",
        "",
        "| # | Conversa | O que mostra |",
        "|---|---|---|",
    ]
    for conv, path in items:
        lines.append(f"| {conv.id[:2]} | [{conv.title}]({path.name}) | {conv.highlights} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gera as conversas de exemplo em examples/.")
    parser.add_argument("--only", help="Gera só as conversas cujo id contém este texto.")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    settings = get_settings()
    base = EmporioAgent(settings)
    configured = resolve_model(settings)
    args.output.mkdir(parents=True, exist_ok=True)
    conversations = load_script()
    selected = [c for c in conversations if not args.only or args.only in c.id]

    for conv in selected:
        fixed = conv.now.replace(tzinfo=STORE_TZ)
        agent = EmporioAgent(settings, model=base.model, repo=base.repo, policies=base.policies,
                             clock=lambda fixed=fixed: fixed, handoffs=HandoffStore(":memory:"))
        session = agent.new_session(f"example-{conv.id}")
        replies = []
        for message in conv.turns:
            reply = session.send(message)
            if reply.error:
                raise SystemExit(f"Falha na conversa {conv.id}: {reply.text}")
            replies.append(reply)
        path = args.output / f"{conv.id}.md"
        path.write_text(render_markdown(conv, replies, configured), encoding="utf-8")
        print(f"✔ {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path}")

    index = args.output / "README.md"
    index.write_text(render_index([(c, args.output / f"{c.id}.md") for c in conversations]), encoding="utf-8")
    print(f"✔ {index}")


if __name__ == "__main__":
    main()
