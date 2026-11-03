"""Configuração da aplicação, lida de variáveis de ambiente ou do arquivo `.env`.

Toda a configuração do modelo de linguagem fica aqui. Para trocar de modelo ou de
provedor basta alterar variáveis de ambiente; nenhum código precisa mudar:

    LLM_MODEL=@preset/emporio-agent          # preset do OpenRouter (padrão)
    LLM_MODEL=openai/gpt-4o-mini             # qualquer modelo do catálogo do OpenRouter
    LLM_BASE_URL=http://localhost:11434/v1   # ou qualquer API compatível com OpenAI (ex.: Ollama)
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Literal
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from emporio.data.paths import PROCESSED_DIR, PROJECT_ROOT

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "@preset/emporio-agent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Modelo de linguagem -------------------------------------------------
    llm_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("LLM_API_KEY", "OPENROUTER_API_KEY")
    )
    llm_base_url: str = Field(default=OPENROUTER_BASE_URL, validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default=DEFAULT_MODEL, validation_alias="LLM_MODEL")
    # Modelo para tarefas auxiliares e baratas (guardrails, avaliação). Vazio = usa LLM_MODEL.
    llm_fast_model: str | None = Field(default=None, validation_alias="LLM_FAST_MODEL")
    # Fallbacks enviados na requisição (só OpenRouter), separados por vírgula. Use quando
    # LLM_MODEL for um modelo concreto; presets já trazem seus próprios fallbacks.
    llm_fallback_models: str = Field(default="", validation_alias="LLM_FALLBACK_MODELS")
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")
    # Limite de tokens da resposta. Sem ele, o OpenRouter reserva crédito para o máximo do
    # modelo (ex.: 16k) e recusa a chamada (402) em chaves com limite de crédito baixo.
    llm_max_tokens: int = Field(default=1024, validation_alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: float = Field(default=60.0, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=2, validation_alias="LLM_MAX_RETRIES")

    # --- Busca no manual de políticas ----------------------------------------
    # Modelo de embeddings (mesmo endpoint e chave do LLM). Vazio = só busca lexical (BM25).
    # Padrões escolhidos pela avaliação (uv run emporio-eval-retrieval --dataset holdout):
    # embeddings puros generalizaram melhor que BM25 e que o híbrido. BM25 é o fallback
    # automático se a API de embeddings falhar.
    embedding_model: str = Field(default="google/gemini-embedding-001", validation_alias="EMBEDDING_MODEL")
    retrieval_mode: Literal["hybrid", "bm25", "embeddings"] = Field(
        default="embeddings", validation_alias="RETRIEVAL_MODE"
    )

    # --- Relógio -------------------------------------------------------------
    # Data/hora fixa para demonstrações e testes reproduzíveis (ex.: 2026-03-25T10:30).
    # Sem fuso, é interpretada no horário da loja (America/Campo_Grande).
    emporio_now: datetime | None = Field(default=None, validation_alias="EMPORIO_NOW")

    # --- Dados ---------------------------------------------------------------
    database_path: Path = Field(default=PROCESSED_DIR / "emporio.db", validation_alias="EMPORIO_DB_PATH")
    # Estado de execução: histórico das conversas e atendimentos encaminhados à equipe.
    state_dir: Path = Field(default=PROJECT_ROOT / "var", validation_alias="EMPORIO_STATE_DIR")

    @property
    def conversations_path(self) -> Path:
        return self.state_dir / "conversations.sqlite"

    @property
    def handoffs_path(self) -> Path:
        return self.state_dir / "handoffs.sqlite"

    @property
    def is_openrouter(self) -> bool:
        return "openrouter.ai" in self.llm_base_url

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
