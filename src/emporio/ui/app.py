"""Interface web (Streamlit) da assistente da Empório da Música.

    uv run streamlit run src/emporio/ui/app.py      # local
    docker compose up                               # em container (http://localhost:8501)

Duas páginas:
- **Chat**: conversas na barra lateral (como nos chats de IA atuais), histórico persistente,
  e um painel em cada resposta com as ferramentas chamadas, seus parâmetros e resultados.
- **Atendimentos**: painel da equipe com os casos encaminhados pela assistente.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from emporio.agent import ChatSession, EmporioAgent, create_agent
from emporio.agent.graph import ToolCallRecord
from emporio.agent.history import conversation_turns
from emporio.agent.memory import list_sessions
from emporio.agent.prompts import ASSISTANT_NAME
from emporio.business_hours import STORE_TZ
from emporio.config import get_settings
from emporio.llm import LLMConfigError, resolve_model

AVATARS = {"user": "🙂", "assistant": "🎸"}
SUGGESTIONS = (
    "Quais opções de violões disponíveis custando até R$1000?",
    "Qual o endereço da loja?",
    "Quanto custa o Takamine GD20?",
    "Me arrependi da minha compra, posso devolver meu pedido?",
)
TOOL_LABELS = {
    "search_products": "Busca no catálogo",
    "get_product_details": "Detalhes do produto",
    "list_categories": "Categorias",
    "list_promotions": "Promoções",
    "get_order_status": "Status do pedido",
    "check_return_eligibility": "Troca e devolução",
    "payment_options": "Formas de pagamento",
    "shipping_quote": "Frete",
    "search_policies": "Manual de políticas",
    "escalate_to_human": "Encaminhamento à equipe",
    "store_status": "Horário da loja",
}


# --- Recursos ------------------------------------------------------------------------------


@st.cache_resource(show_spinner="Preparando a assistente…")
def get_agent(now_iso: str | None) -> EmporioAgent:
    """Um agente por data simulada (o relógio é fixo por agente); todos usam o mesmo SQLite."""
    settings = get_settings()
    if now_iso:
        settings = settings.model_copy(update={"emporio_now": datetime.fromisoformat(now_iso)})
    return create_agent(settings, persistent=True)


def get_session(agent: EmporioAgent, now_iso: str | None, thread_id: str) -> ChatSession:
    # Uma ChatSession por conversa e por navegador: guarda o limite de tentativas de verificação.
    sessions: dict[tuple[str | None, str], ChatSession] = st.session_state.setdefault("sessions", {})
    key = (now_iso, thread_id)
    if key not in sessions:
        sessions[key] = agent.new_session(thread_id)
    return sessions[key]


def new_conversation() -> None:
    st.session_state.thread_id = uuid.uuid4().hex


# --- Componentes ---------------------------------------------------------------------------


def render_tool_calls(calls: list[ToolCallRecord]) -> None:
    label = f"🔧 {len(calls)} ferramenta{'s' if len(calls) > 1 else ''}: " + ", ".join(
        TOOL_LABELS.get(c.name, c.name) for c in calls
    )
    with st.expander(label):
        for call in calls:
            st.markdown(f"**`{call.name}`** · {TOOL_LABELS.get(call.name, '')}")
            st.caption("Parâmetros")
            st.code(json.dumps(call.args, ensure_ascii=False, indent=2), language="json")
            st.caption("Resultado")
            try:
                st.json(json.loads(call.output), expanded=False)
            except (json.JSONDecodeError, TypeError):
                st.code(call.output or "(vazio)")


def render_assistant(text: str, calls: list[ToolCallRecord], show_tools: bool, error: bool = False) -> None:
    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        (st.error if error else st.markdown)(text)
        if show_tools and calls:
            render_tool_calls(calls)


def sidebar(agent: EmporioAgent) -> tuple[bool, str | None]:
    with st.sidebar:
        st.markdown("## 🎸 Empório da Música")
        st.button("➕ Nova conversa", use_container_width=True, on_click=new_conversation)

        st.markdown("#### Conversas")
        sessions = list_sessions(agent.checkpointer, limit=30)
        if not sessions:
            st.caption("Nenhuma conversa ainda.")
        for info in sessions:
            current = info.thread_id == st.session_state.thread_id
            st.button(
                info.title or "(sem título)",
                key=f"conv-{info.thread_id}",
                help=f"{info.updated_at:%d/%m/%Y %H:%M} · {info.messages} mensagens",
                type="primary" if current else "secondary",
                use_container_width=True,
                on_click=lambda tid=info.thread_id: st.session_state.update(thread_id=tid),
            )

        st.divider()
        show_tools = st.toggle("Mostrar ferramentas chamadas", value=True)
        with st.expander("⚙️ Simulação e privacidade"):
            simulate = st.checkbox("Simular data/hora", help="Os pedidos da base são de 2025-2026.")
            now_iso = None
            if simulate:
                day = st.date_input("Data", value=date(2026, 3, 2), format="DD/MM/YYYY")
                hour = st.time_input("Hora", value=time(10, 30), step=1800)
                now_iso = datetime.combine(day, hour).isoformat(timespec="minutes")
            if st.button("🗑️ Apagar esta conversa", use_container_width=True,
                         help="Remove o histórico desta conversa (LGPD)."):
                agent.new_session(st.session_state.thread_id).forget()
                new_conversation()
                st.rerun()
        st.caption(f"Modelo: `{resolve_model(agent.settings)}`")
    return show_tools, now_iso


# --- Páginas -------------------------------------------------------------------------------


def chat_page() -> None:
    st.session_state.setdefault("thread_id", uuid.uuid4().hex)
    try:
        base_agent = get_agent(None)
    except LLMConfigError as exc:
        st.error(f"Configuração do modelo ausente: {exc}")
        st.stop()
    show_tools, now_iso = sidebar(base_agent)
    agent = get_agent(now_iso) if now_iso else base_agent
    session = get_session(agent, now_iso, st.session_state.thread_id)

    now = agent.clock()
    st.markdown(f"### Fale com a {ASSISTANT_NAME}")
    st.caption(f"Assistente virtual da Empório da Música · {now.astimezone(STORE_TZ):%d/%m/%Y %H:%M}"
               + (" (simulado)" if now_iso else ""))

    turns = conversation_turns(session.history())
    for turn in turns:
        with st.chat_message("user", avatar=AVATARS["user"]):
            st.markdown(turn.user)
        render_assistant(turn.reply, turn.tool_calls, show_tools)

    prompt = st.chat_input("Escreva sua mensagem…")
    if not turns and not prompt:
        st.markdown(f"Oi! Eu sou a **{ASSISTANT_NAME}**. Posso ajudar com produtos, preços, pedidos, "
                    "trocas, frete e horários. Experimente:")
        columns = st.columns(2)
        for i, suggestion in enumerate(SUGGESTIONS):
            if columns[i % 2].button(suggestion, use_container_width=True, key=f"sug-{i}"):
                prompt = suggestion

    if prompt:
        with st.chat_message("user", avatar=AVATARS["user"]):
            st.markdown(prompt)
        with st.spinner(f"{ASSISTANT_NAME} está digitando…"):
            reply = session.send(prompt)
        render_assistant(reply.text, reply.tool_calls, show_tools, error=reply.error)
        st.rerun()  # atualiza a lista de conversas e o histórico (com a mensagem já mascarada)


def handoffs_page() -> None:
    st.markdown("### 📋 Atendimentos encaminhados")
    st.caption("Casos registrados pela assistente para a equipe (reclamações, defeitos, devoluções…).")
    try:
        agent = get_agent(None)
    except LLMConfigError as exc:
        st.error(f"Configuração do modelo ausente: {exc}")
        st.stop()
    include_closed = st.toggle("Incluir encerrados")
    tickets = agent.handoffs.list(include_closed=include_closed)
    if not tickets:
        st.info("Nenhum atendimento " + ("registrado." if include_closed else "aberto."))
        return
    st.dataframe(
        pd.DataFrame([{
            "Protocolo": t.code, "Aberto em": t.created_at.strftime("%d/%m %H:%M"), "Motivo": t.reason,
            "Cliente": t.customer_name, "Contato": t.contact, "Pedido": t.order_id,
            "Resumo": t.summary, "Status": t.status,
        } for t in tickets]),
        hide_index=True, use_container_width=True,
    )
    open_tickets = {t.code: t.id for t in tickets if t.status == "open"}
    if open_tickets:
        code = st.selectbox("Encerrar atendimento", list(open_tickets))
        if st.button("Encerrar"):
            agent.handoffs.close(open_tickets[code])
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="Empório da Música · Assistente", page_icon="🎸", layout="wide")
    navigation = st.navigation([
        st.Page(chat_page, title="Chat", icon="💬", default=True),
        st.Page(handoffs_page, title="Atendimentos", icon="📋"),
    ])
    navigation.run()


main()
