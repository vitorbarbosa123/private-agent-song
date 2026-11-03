"""Estado compartilhado pelas ferramentas durante uma conversa."""

from __future__ import annotations

from dataclasses import dataclass

from emporio.business_hours import Clock, make_clock
from emporio.config import Settings, get_settings
from emporio.rag.retriever import PolicyRetriever
from emporio.repository import StoreRepository, open_repository

MAX_AUTH_ATTEMPTS = 3


@dataclass
class ToolContext:
    """Um contexto por conversa: o repositório pode ser compartilhado, mas o contador de
    tentativas de verificação de identidade é da sessão (proteção contra força bruta)."""

    repo: StoreRepository
    clock: Clock
    policies: PolicyRetriever | None = None
    max_auth_attempts: int = MAX_AUTH_ATTEMPTS
    failed_auth_attempts: int = 0

    @classmethod
    def from_settings(cls, settings: Settings | None = None, repo: StoreRepository | None = None) -> ToolContext:
        s = settings or get_settings()
        repository = repo or open_repository(s)  # gera data/processed se ainda não existir
        return cls(repo=repository, clock=make_clock(s), policies=PolicyRetriever.from_settings(s))

    @property
    def auth_locked(self) -> bool:
        return self.failed_auth_attempts >= self.max_auth_attempts
