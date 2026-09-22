"""Structured diagnostics shared by configuration and doctor services."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class Diagnostic:
    """A bounded diagnostic that avoids embedding private source contents."""

    code: str
    severity: Severity
    message: str
    remediation: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)
