"""Testes da API REST com o agente roteirizado (sem rede)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from emporio.api import create_app
from emporio.repository import StoreRepository
from tests.test_agent import tool_call
from tests.test_memory_handoff import CASE, _agent


@pytest.fixture
def client_factory(tmp_path: Path, repo: StoreRepository):
    def factory(*responses: AIMessage, api_key: str | None = "") -> tuple[TestClient, object]:
        agent = _agent(tmp_path, repo, *responses)
        client = TestClient(create_app(agent, api_key=api_key))
        client.__enter__()  # dispara o lifespan
        return client, agent

    return factory


def test_health(client_factory) -> None:
    client, _ = client_factory()
    assert client.get("/health").json()["status"] == "ok"


def test_conversation_flow(client_factory) -> None:
    client, _ = client_factory(
        tool_call("get_product_details", {"name": "Takamine GD20"}),
        AIMessage("O Takamine GD20 custa R$ 2.199,00."),
    )
    conversation_id = client.post("/conversations").json()["id"]

    response = client.post(f"/conversations/{conversation_id}/messages?include_tools=true",
                           json={"message": "Quanto custa o Takamine GD20?"})
    body = response.json()
    assert response.status_code == 200 and not body["error"]
    assert body["reply"] == "O Takamine GD20 custa R$ 2.199,00."
    assert body["tool_calls"][0]["name"] == "get_product_details"

    history = client.get(f"/conversations/{conversation_id}").json()
    assert history[0]["user"] == "Quanto custa o Takamine GD20?"
    assert "2.199,00" in history[0]["tool_calls"][0]["output"]

    listed = client.get("/conversations").json()
    assert listed[0]["id"] == conversation_id and listed[0]["title"].startswith("Quanto custa")


def test_tools_hidden_by_default(client_factory) -> None:
    client, _ = client_factory(AIMessage("Oi!"))
    body = client.post("/conversations/c1/messages", json={"message": "Oi"}).json()
    assert body["tool_calls"] is None


def test_delete_conversation_lgpd(client_factory) -> None:
    client, _ = client_factory(AIMessage("Oi!"))
    client.post("/conversations/apagar/messages", json={"message": "meu email é ana@x.com"})
    assert client.delete("/conversations/apagar").status_code == 204
    assert client.get("/conversations/apagar").status_code == 404


def test_validation(client_factory) -> None:
    client, _ = client_factory()
    assert client.post("/conversations/c1/messages", json={"message": ""}).status_code == 422
    assert client.post("/conversations/c1/messages", json={"message": "x" * 5000}).status_code == 422


def test_handoffs_endpoints(client_factory) -> None:
    client, _ = client_factory(
        tool_call("escalate_to_human", {"reason": "reclamacao", **CASE}),
        AIMessage("Registrei no protocolo ATD-00001."),
    )
    client.post("/conversations/r1/messages", json={"message": "Quero reclamar"})
    tickets = client.get("/handoffs").json()
    assert tickets[0]["code"] == "ATD-00001" and tickets[0]["order_id"] == 7
    assert client.post(f"/handoffs/{tickets[0]['id']}/close").json() == {"status": "closed"}
    assert client.get("/handoffs").json() == []
    assert client.post(f"/handoffs/{tickets[0]['id']}/close").status_code == 404


def test_api_key_required_when_configured(client_factory) -> None:
    client, _ = client_factory(AIMessage("Oi!"), api_key="segredo")
    assert client.get("/health").status_code == 200  # healthcheck é público
    assert client.post("/conversations").status_code == 401
    assert client.post("/conversations", headers={"X-API-Key": "errada"}).status_code == 401
    assert client.post("/conversations", headers={"X-API-Key": "segredo"}).status_code == 201
