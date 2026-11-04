"""Testes do gerador de conversas de exemplo (sem rede)."""

from __future__ import annotations

from emporio.agent import AgentReply
from emporio.agent.graph import ToolCallRecord
from emporio.evals.examples import load_script, render_index, render_markdown


def test_script_has_three_to_five_conversations() -> None:
    conversations = load_script()
    assert 3 <= len(conversations) <= 5  # exigência do desafio
    assert all(c.turns for c in conversations)


def test_render_markdown_includes_turns_and_tools() -> None:
    conv = load_script()[1]
    replies = [AgentReply(f"resposta {i}", [ToolCallRecord("get_product_details", {"name": "x"}, '{"a": 1}')],
                          cost_usd=0.01, model="anthropic/claude-haiku-4.5") for i in range(len(conv.turns))]
    md = render_markdown(conv, replies, "@preset/emporio-agent")
    assert md.startswith(f"# {conv.title}")
    assert "@preset/emporio-agent → anthropic/claude-haiku-4.5" in md
    assert all(turn in md for turn in conv.turns)
    assert "<details><summary>🔧 Ferramentas chamadas: `get_product_details`" in md


def test_render_index_links_every_conversation(tmp_path) -> None:
    conversations = load_script()
    index = render_index([(c, tmp_path / f"{c.id}.md") for c in conversations])
    assert all(f"({c.id}.md)" in index for c in conversations)
