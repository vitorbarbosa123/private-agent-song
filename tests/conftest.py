from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from emporio.data.pipeline import run_pipeline, write_outputs
from emporio.repository import StoreRepository


@pytest.fixture(scope="session")
def database_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Banco gerado do zero a partir dos dados brutos, isolado do data/processed local."""
    out_dir = tmp_path_factory.mktemp("processed")
    write_outputs(run_pipeline(), out_dir)
    return out_dir / "emporio.db"


@pytest.fixture(scope="session")
def repo(database_path: Path) -> Iterator[StoreRepository]:
    with StoreRepository(database_path) as repository:
        yield repository
