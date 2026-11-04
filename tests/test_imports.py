"""Cada módulo precisa importar sozinho, num processo novo (pega imports circulares)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
# Módulos que outros importam ou que são pontos de entrada: é onde ciclos aparecem.
MODULES = [
    "emporio.config", "emporio.llm", "emporio.observability", "emporio.privacy", "emporio.handoff",
    "emporio.policy_rules", "emporio.business_hours", "emporio.cli", "emporio.agent.graph",
    "emporio.agent.guards", "emporio.agent.memory", "emporio.tools.registry",
    "emporio.repository.repository", "emporio.rag.retriever", "emporio.evals.agent_eval",
    "emporio.data.pipeline",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_in_isolation(module: str) -> None:
    result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True,
                            env={"PYTHONPATH": str(SRC), "PATH": ""}, timeout=60)
    assert result.returncode == 0, result.stderr[-800:]
