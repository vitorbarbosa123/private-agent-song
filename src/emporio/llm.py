"""Fábrica do modelo de linguagem.

Usamos a API compatível com OpenAI, o que permite apontar para o OpenRouter (padrão),
para a própria OpenAI ou para um modelo local (Ollama, LM Studio, vLLM) só trocando
`LLM_BASE_URL`, `LLM_API_KEY` e `LLM_MODEL`. Ver `emporio.config`.

Para conferir a configuração sem rodar o agente:

    uv run emporio-llm-check
"""

from __future__ import annotations

import sys
from typing import Literal

from langchain_openai import ChatOpenAI

from emporio.config import Settings, get_settings

Role = Literal["main", "fast"]
APP_TITLE = "Emporio da Musica - Agente de Atendimento"
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


class LLMConfigError(RuntimeError):
    """Configuração do modelo ausente ou inválida."""


def resolve_model(settings: Settings, role: Role = "main") -> str:
    if role == "fast" and settings.llm_fast_model:
        return settings.llm_fast_model
    return settings.llm_model


def build_chat_model(settings: Settings | None = None, *, role: Role = "main") -> ChatOpenAI:
    """Cria o cliente de chat configurado. `role="fast"` usa LLM_FAST_MODEL, se definido."""
    s = settings or get_settings()
    model = resolve_model(s, role)

    if s.llm_api_key is not None:
        api_key = s.llm_api_key.get_secret_value()
    elif any(host in s.llm_base_url for host in _LOCAL_HOSTS):
        api_key = "not-needed"  # servidores locais costumam ignorar a chave
    else:
        raise LLMConfigError(
            "Nenhuma chave de API configurada. Defina LLM_API_KEY (ou OPENROUTER_API_KEY) "
            "no arquivo .env. Veja .env.example."
        )

    extra_body: dict[str, object] = {}
    headers: dict[str, str] = {}
    if s.is_openrouter:
        headers["X-Title"] = APP_TITLE  # identifica o app no painel do OpenRouter
        if s.fallback_models:
            # O OpenRouter tenta os modelos em ordem caso o primeiro falhe.
            extra_body["models"] = [model, *s.fallback_models]

    return ChatOpenAI(
        model=model,
        base_url=s.llm_base_url,
        api_key=api_key,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout=s.llm_timeout_seconds,
        max_retries=s.llm_max_retries,
        default_headers=headers or None,
        extra_body=extra_body or None,
    )


def describe(settings: Settings) -> str:
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    masked = f"{key[:6]}…{key[-4:]}" if len(key) > 12 else ("(definida)" if key else "(ausente)")
    lines = [
        f"Endpoint:    {settings.llm_base_url}",
        f"Modelo:      {settings.llm_model}",
        f"Modelo fast: {settings.llm_fast_model or '(usa o principal)'}",
        f"Fallbacks:   {', '.join(settings.fallback_models) or '(nenhum na requisição)'}",
        f"Chave:       {masked}",
    ]
    return "\n".join(lines)


def _hint(exc: Exception) -> str:
    """Orientação para os erros de configuração mais comuns do OpenRouter."""
    text = str(exc)
    if "ZDR" in text or "guardrail" in text:
        return ("Dica: um guardrail do workspace (ex.: Zero Data Retention) excluiu todos os "
                "endpoints compatíveis. Ajuste os Guardrails do workspace (link na mensagem acima) ou escolha "
                "outro modelo em LLM_MODEL / no preset.")
    if "402" in text or "credits" in text:
        return "Dica: crédito insuficiente para a chave. Reduza LLM_MAX_TOKENS ou aumente o limite da chave."
    if "401" in text:
        return "Dica: chave inválida. Confira LLM_API_KEY no .env."
    return ""


def _check_tool_calling(settings: Settings) -> str:
    """O agente depende de chamada de ferramentas: confirma que o modelo a suporta."""
    from langchain_core.tools import tool

    @tool
    def consultar_preco(produto: str) -> str:
        """Consulta o preço de um produto da loja pelo nome."""
        return "R$ 100,00"

    response = build_chat_model(settings).bind_tools([consultar_preco]).invoke(
        "Use a ferramenta para consultar o preço do Takamine GD20."
    )
    if not response.tool_calls:
        raise RuntimeError("o modelo respondeu sem chamar a ferramenta (suporte a tools ausente?)")
    return response.response_metadata.get("model_name", "?")


def main() -> None:
    """Mostra a configuração ativa e testa uma chamada simples e uma com ferramentas."""
    settings = get_settings()
    print(describe(settings))
    checks = (
        ("Chamada simples", lambda: build_chat_model(settings)
            .invoke("Responda apenas com a palavra: ok").response_metadata.get("model_name", "?")),
        ("Chamada com ferramentas", lambda: _check_tool_calling(settings)),
    )
    print()
    failed = False
    for label, check in checks:
        try:
            served_by = check()
        except LLMConfigError as exc:
            sys.exit(f"Erro de configuração: {exc}")
        except Exception as exc:  # noqa: BLE001 — erro de rede/autenticação mostrado ao usuário
            failed = True
            print(f"[FALHOU] {label}: {type(exc).__name__}: {str(exc)[:300]}")
            if hint := _hint(exc):
                print(f"         {hint}")
        else:
            print(f"[OK]     {label} (atendido por {served_by})")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
