"""Runtime diagnostics for the local configuration."""

from __future__ import annotations

import platform
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass

from stellaris_supporter import __version__
from stellaris_supporter.config import ConfigResult, validate_paths
from stellaris_supporter.diagnostics import Diagnostic

FtsProbe = Callable[[], bool]


@dataclass(frozen=True)
class RuntimeCapabilities:
    application_version: str
    python_version: str
    sqlite_version: str
    fts5_available: bool
    network_enabled: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DoctorReport:
    status: str
    settings: dict[str, object]
    runtime: RuntimeCapabilities
    diagnostics: tuple[Diagnostic, ...]

    @property
    def exit_code(self) -> int:
        if any(d.code in {"PATH_REJECTED", "NETWORK_REJECTED"} for d in self.diagnostics):
            return 4
        if any(d.severity == "error" for d in self.diagnostics):
            return 3
        return 0

    def to_dict(self, *, public: bool = False) -> dict[str, object]:
        settings = dict(self.settings)
        if public:
            settings["config_path"] = "<CONFIG_PATH>"
            settings["game_root"] = "<GAME_ROOT>" if settings.get("game_root") is not None else None
            settings["data_dir"] = "<DATA_DIR>"
        return {
            "schema_version": 1,
            "status": self.status,
            "settings": settings,
            "runtime": self.runtime.to_dict(),
            "diagnostics": [
                (
                    {
                        "code": d.code,
                        "severity": d.severity,
                        "message": f"Diagnostic {d.code}.",
                        "remediation": None,
                    }
                    if public
                    else d.to_dict()
                )
                for d in self.diagnostics
            ],
        }


def probe_fts5() -> bool:
    try:
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE probe_fts USING fts5(text)")
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return True


def probe_runtime(*, fts_probe: FtsProbe = probe_fts5) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        application_version=__version__,
        python_version=platform.python_version(),
        sqlite_version=sqlite3.sqlite_version,
        fts5_available=fts_probe(),
        network_enabled=False,
    )


def run_doctor(config_result: ConfigResult, *, fts_probe: FtsProbe = probe_fts5) -> DoctorReport:
    diagnostics = list(config_result.diagnostics)
    diagnostics.extend(validate_paths(config_result.settings))
    runtime = probe_runtime(fts_probe=fts_probe)

    if runtime.fts5_available:
        diagnostics.append(Diagnostic("SQLITE_FTS5_AVAILABLE", "info", "SQLite FTS5 is available."))
    else:
        diagnostics.append(
            Diagnostic(
                "SQLITE_FTS5_UNAVAILABLE",
                "warning",
                "SQLite FTS5 is unavailable; later search must use its documented fallback.",
                "Use a Python/SQLite build with FTS5 for the preferred lexical index.",
            )
        )
    diagnostics.append(
        Diagnostic(
            "NETWORK_DISABLED",
            "info",
            "Network access is disabled by the v0.1 configuration policy.",
        )
    )

    if any(d.severity == "error" for d in diagnostics):
        status = "error"
    elif any(d.severity == "warning" for d in diagnostics):
        status = "warning"
    else:
        status = "ok"

    return DoctorReport(
        status=status,
        settings=config_result.settings.to_dict(),
        runtime=runtime,
        diagnostics=tuple(diagnostics),
    )
