"""Registro estruturado dos problemas de qualidade encontrados nos dados."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import StrEnum

import pandas as pd


class Severity(StrEnum):
    INFO = "info"  # observação, nenhum impacto no atendimento
    WARNING = "warning"  # inconsistência tratada/sinalizada; o agente deve considerar
    ERROR = "error"  # dado inválido, registro descartado ou valor anulado


@dataclass(frozen=True)
class Issue:
    table: str
    record_id: str | None
    rule: str
    severity: Severity
    message: str
    action: str


class IssueLog:
    """Acumula os problemas encontrados ao longo do pipeline."""

    def __init__(self) -> None:
        self._issues: list[Issue] = []

    def add(
        self,
        table: str,
        record_id: object,
        rule: str,
        severity: Severity,
        message: str,
        action: str,
    ) -> None:
        rid = None if record_id is None else str(record_id)
        self._issues.append(Issue(table, rid, rule, severity, message, action))

    def __iter__(self) -> Iterator[Issue]:
        return iter(self._issues)

    def __len__(self) -> int:
        return len(self._issues)

    def by_rule(self, rule: str) -> list[Issue]:
        return [i for i in self._issues if i.rule == rule]

    def record_ids(self, rule: str) -> set[str]:
        return {i.record_id for i in self.by_rule(rule) if i.record_id is not None}

    def to_frame(self) -> pd.DataFrame:
        columns = ["table", "record_id", "rule", "severity", "message", "action"]
        return pd.DataFrame([asdict(i) for i in self._issues], columns=columns)
