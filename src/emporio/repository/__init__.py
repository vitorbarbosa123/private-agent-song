"""Camada de acesso aos dados tratados."""

from __future__ import annotations

from emporio.config import Settings, get_settings
from emporio.repository.repository import DatabaseNotFoundError, StoreRepository


def open_repository(settings: Settings | None = None, *, build_if_missing: bool = True) -> StoreRepository:
    """Abre o repositório. Se o banco ainda não existe, roda o pipeline de dados antes."""
    s = settings or get_settings()
    if not s.database_path.exists() and build_if_missing:
        from emporio.data.pipeline import run_pipeline, write_outputs

        write_outputs(run_pipeline(), s.database_path.parent)
    return StoreRepository(s.database_path)


__all__ = ["DatabaseNotFoundError", "StoreRepository", "open_repository"]
