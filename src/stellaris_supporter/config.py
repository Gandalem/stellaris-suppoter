"""Configuration loading and path policy."""

from __future__ import annotations

import os
import platform
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from stellaris_supporter.diagnostics import Diagnostic

DEFAULT_FILE_BYTES = 16 * 1024 * 1024
DEFAULT_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_DEPTH = 128
DEFAULT_MAX_FILES = 50_000
DEFAULT_QUERY_CHARS = 512
DEFAULT_MAX_RESULTS = 100

_ALLOWED_TOP_LEVEL = {"schema_version", "game_root", "data_dir", "language", "network", "limits"}
_ALLOWED_NETWORK = {"enabled"}
_ALLOWED_LIMITS = {
    "file_bytes",
    "total_bytes",
    "max_depth",
    "max_files",
    "query_chars",
    "max_results",
}
_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
_PATH_ERRORS = (OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class Limits:
    file_bytes: int = DEFAULT_FILE_BYTES
    total_bytes: int = DEFAULT_TOTAL_BYTES
    max_depth: int = DEFAULT_MAX_DEPTH
    max_files: int = DEFAULT_MAX_FILES
    query_chars: int = DEFAULT_QUERY_CHARS
    max_results: int = DEFAULT_MAX_RESULTS

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class Settings:
    config_path: Path
    game_root: Path | None
    data_dir: Path
    language: str
    network_enabled: bool
    limits: Limits

    def to_dict(self) -> dict[str, object]:
        return {
            "config_path": str(self.config_path),
            "game_root": str(self.game_root) if self.game_root is not None else None,
            "data_dir": str(self.data_dir),
            "language": self.language,
            "network_enabled": self.network_enabled,
            "limits": self.limits.to_dict(),
        }


@dataclass(frozen=True)
class ConfigResult:
    settings: Settings
    diagnostics: tuple[Diagnostic, ...]


Reader = Callable[[Path], bytes]
AccessChecker = Callable[[Path, int], bool]


def default_config_path(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    system_name = (system or platform.system()).lower()
    environment = env if env is not None else os.environ
    home_dir = home if home is not None else Path.home()
    if system_name == "windows":
        base = Path(environment.get("LOCALAPPDATA", str(home_dir / "AppData" / "Local")))
        return base / "StellarisSupporter" / "config.toml"
    if system_name == "darwin":
        return home_dir / "Library" / "Application Support" / "StellarisSupporter" / "config.toml"
    raw_base = environment.get("XDG_CONFIG_HOME")
    candidate = Path(raw_base) if raw_base else None
    base = candidate if candidate is not None and candidate.is_absolute() else home_dir / ".config"
    return base / "stellaris-supporter" / "config.toml"


def default_data_dir(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    system_name = (system or platform.system()).lower()
    environment = env if env is not None else os.environ
    home_dir = home if home is not None else Path.home()
    if system_name == "windows":
        base = Path(environment.get("LOCALAPPDATA", str(home_dir / "AppData" / "Local")))
        return base / "StellarisSupporter" / "data"
    if system_name == "darwin":
        return home_dir / "Library" / "Application Support" / "StellarisSupporter" / "data"
    raw_base = environment.get("XDG_DATA_HOME")
    candidate = Path(raw_base) if raw_base else None
    base = candidate if candidate is not None and candidate.is_absolute() else home_dir / ".local" / "share"
    return base / "stellaris-supporter"


def _default_reader(path: Path) -> bytes:
    return path.read_bytes()


def _parse_toml(data: bytes) -> tuple[dict[str, Any], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    try:
        text_value = data.decode("utf-8")
    except UnicodeDecodeError:
        diagnostics.append(
            Diagnostic(
                "CONFIG_INVALID_ENCODING",
                "error",
                "Configuration must be valid UTF-8.",
                "Save the TOML file as UTF-8 and retry.",
            )
        )
        return {}, diagnostics
    try:
        return tomllib.loads(text_value), diagnostics
    except tomllib.TOMLDecodeError:
        diagnostics.append(
            Diagnostic(
                "CONFIG_INVALID_TOML",
                "error",
                "Configuration TOML is malformed.",
                "Fix TOML syntax before running the command again.",
            )
        )
        return {}, diagnostics


def _validate_keys(parsed: Mapping[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    unknown = sorted(set(parsed) - _ALLOWED_TOP_LEVEL)
    if unknown:
        diagnostics.append(
            Diagnostic(
                "CONFIG_UNKNOWN_KEY",
                "error",
                "Unknown top-level configuration key(s) are present.",
                "Remove misspelled or unsupported keys.",
            )
        )

    network = parsed.get("network", {})
    if not isinstance(network, dict):
        diagnostics.append(Diagnostic("CONFIG_INVALID_TYPE", "error", "[network] must be a TOML table."))
    else:
        extra = sorted(set(network) - _ALLOWED_NETWORK)
        if extra:
            diagnostics.append(
                Diagnostic("CONFIG_UNKNOWN_KEY", "error", "Unknown [network] key(s) are present.")
            )

    limits = parsed.get("limits", {})
    if not isinstance(limits, dict):
        diagnostics.append(Diagnostic("CONFIG_INVALID_TYPE", "error", "[limits] must be a TOML table."))
    else:
        extra = sorted(set(limits) - _ALLOWED_LIMITS)
        if extra:
            diagnostics.append(
                Diagnostic("CONFIG_UNKNOWN_KEY", "error", "Unknown [limits] key(s) are present.")
            )
    return diagnostics


def _resolve_path(
    value: str,
    *,
    base: Path,
    diagnostics: list[Diagnostic],
    field: str,
) -> Path | None:
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base / path
        return path.resolve(strict=False)
    except _PATH_ERRORS:
        diagnostics.append(
            Diagnostic(
                "PATH_INVALID",
                "error",
                f"{field} contains a path that cannot be resolved.",
                "Use a valid path without invalid characters or unknown user expansion.",
            )
        )
        return None


def _safe_exists(path: Path, diagnostics: list[Diagnostic], *, code: str, label: str) -> bool | None:
    try:
        return path.exists()
    except _PATH_ERRORS:
        diagnostics.append(
            Diagnostic(
                code,
                "error",
                f"{label} cannot be inspected.",
                "Check the path syntax and parent-directory permissions.",
            )
        )
        return None


def _read_positive_int(
    limits: Mapping[str, Any],
    key: str,
    default: int,
    diagnostics: list[Diagnostic],
) -> int:
    value = limits.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        diagnostics.append(
            Diagnostic("CONFIG_INVALID_LIMIT", "error", f"limits.{key} must be a positive integer.")
        )
        return default
    return value


def load_settings(
    config_path: Path | None,
    *,
    overrides: Mapping[str, str | None] | None = None,
    cwd: Path | None = None,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    reader: Reader = _default_reader,
) -> ConfigResult:
    environment = env if env is not None else os.environ
    diagnostics: list[Diagnostic] = []
    raw_cwd = cwd if cwd is not None else Path.cwd()
    try:
        current_dir = raw_cwd.resolve(strict=False)
    except _PATH_ERRORS:
        current_dir = raw_cwd
        diagnostics.append(
            Diagnostic("CWD_INVALID", "error", "Current working directory cannot be resolved.")
        )

    explicit_config = config_path is not None
    selected_config = config_path or default_config_path(system=system, env=environment, home=home)
    if not selected_config.is_absolute():
        selected_config = current_dir / selected_config
    try:
        selected_config = selected_config.resolve(strict=False)
        config_exists = _safe_exists(
            selected_config,
            diagnostics,
            code="CONFIG_PATH_INACCESSIBLE",
            label="Configuration path",
        )
    except _PATH_ERRORS:
        config_exists = None
        diagnostics.append(
            Diagnostic(
                "CONFIG_PATH_INVALID",
                "error",
                "Configuration path cannot be resolved.",
                "Use a valid --config path.",
            )
        )

    parsed: dict[str, Any] = {}
    if config_exists is True:
        try:
            data = reader(selected_config)
        except OSError:
            diagnostics.append(
                Diagnostic(
                    "CONFIG_UNREADABLE",
                    "error",
                    "Configuration file cannot be read.",
                    "Check file permissions and the --config path.",
                )
            )
        else:
            parsed, parse_diagnostics = _parse_toml(data)
            diagnostics.extend(parse_diagnostics)
            diagnostics.extend(_validate_keys(parsed))
    elif config_exists is False and explicit_config:
        diagnostics.append(
            Diagnostic(
                "CONFIG_MISSING",
                "error",
                "The explicitly selected configuration file does not exist.",
                "Create the file or pass a different --config path.",
            )
        )
    elif config_exists is False:
        diagnostics.append(
            Diagnostic(
                "CONFIG_DEFAULT_MISSING",
                "info",
                "No default configuration file was found; CLI values and safe defaults are in use.",
            )
        )

    schema_version = parsed.get("schema_version", 1)
    if type(schema_version) is not int or schema_version != 1:
        diagnostics.append(
            Diagnostic("CONFIG_SCHEMA_UNSUPPORTED", "error", "schema_version must be integer 1.")
        )

    cli = dict(overrides or {})
    config_base = selected_config.parent

    def choose_path(name: str) -> Path | None:
        override = cli.get(name)
        if override is not None:
            if not isinstance(override, str) or not override.strip():
                diagnostics.append(
                    Diagnostic("CONFIG_INVALID_TYPE", "error", f"{name} override must be a path string.")
                )
                return None
            return _resolve_path(
                override,
                base=current_dir,
                diagnostics=diagnostics,
                field=f"{name} override",
            )
        value = parsed.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            diagnostics.append(
                Diagnostic("CONFIG_INVALID_TYPE", "error", f"{name} must be a non-empty path string.")
            )
            return None
        return _resolve_path(value, base=config_base, diagnostics=diagnostics, field=name)

    game_root = choose_path("game_root")
    if game_root is None:
        diagnostics.append(
            Diagnostic(
                "GAME_ROOT_REQUIRED",
                "error",
                "game_root is not configured; automatic game discovery is disabled.",
                "Set game_root in TOML or pass --game-root explicitly.",
            )
        )

    data_dir = choose_path("data_dir")
    if data_dir is None:
        raw_data_dir = default_data_dir(system=system, env=environment, home=home)
        resolved_data_dir = _resolve_path(
            str(raw_data_dir),
            base=current_dir,
            diagnostics=diagnostics,
            field="data_dir default",
        )
        data_dir = resolved_data_dir if resolved_data_dir is not None else raw_data_dir

    language_value: object = (
        cli.get("language") if cli.get("language") is not None else parsed.get("language", "ko")
    )
    if not isinstance(language_value, str) or not _LANGUAGE_RE.fullmatch(language_value):
        diagnostics.append(
            Diagnostic(
                "CONFIG_INVALID_LANGUAGE",
                "error",
                "language must contain 2-32 letters, digits, hyphens, or underscores.",
            )
        )
        language = "ko"
    else:
        language = language_value

    network = parsed.get("network", {})
    if isinstance(network, dict):
        requested = network.get("enabled", False)
        if not isinstance(requested, bool):
            diagnostics.append(
                Diagnostic("CONFIG_INVALID_TYPE", "error", "network.enabled must be true or false.")
            )
        elif requested:
            diagnostics.append(
                Diagnostic(
                    "NETWORK_REJECTED",
                    "error",
                    "network.enabled=true is not allowed in the v0.1 local configuration.",
                    "Set network.enabled=false. External providers are a later opt-in feature.",
                )
            )

    limits_raw = parsed.get("limits", {})
    if not isinstance(limits_raw, dict):
        limits_raw = {}
    limits = Limits(
        file_bytes=_read_positive_int(limits_raw, "file_bytes", DEFAULT_FILE_BYTES, diagnostics),
        total_bytes=_read_positive_int(limits_raw, "total_bytes", DEFAULT_TOTAL_BYTES, diagnostics),
        max_depth=_read_positive_int(limits_raw, "max_depth", DEFAULT_MAX_DEPTH, diagnostics),
        max_files=_read_positive_int(limits_raw, "max_files", DEFAULT_MAX_FILES, diagnostics),
        query_chars=_read_positive_int(limits_raw, "query_chars", DEFAULT_QUERY_CHARS, diagnostics),
        max_results=_read_positive_int(limits_raw, "max_results", DEFAULT_MAX_RESULTS, diagnostics),
    )
    settings = Settings(
        config_path=selected_config,
        game_root=game_root,
        data_dir=data_dir,
        language=language,
        network_enabled=False,
        limits=limits,
    )
    return ConfigResult(settings, tuple(diagnostics))


def paths_overlap(first: Path, second: Path) -> bool:
    first_resolved = first.resolve(strict=False)
    second_resolved = second.resolve(strict=False)
    return (
        first_resolved == second_resolved
        or first_resolved in second_resolved.parents
        or second_resolved in first_resolved.parents
    )


def validate_paths(
    settings: Settings,
    *,
    access_checker: AccessChecker = os.access,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    game_root = settings.game_root
    data_dir = settings.data_dir

    if game_root is not None:
        try:
            overlap = paths_overlap(game_root, data_dir)
        except _PATH_ERRORS:
            overlap = False
            diagnostics.append(
                Diagnostic(
                    "PATH_INVALID",
                    "error",
                    "Configured game/data paths cannot be resolved safely.",
                )
            )
        if overlap:
            diagnostics.append(
                Diagnostic(
                    "PATH_REJECTED",
                    "error",
                    "game_root and data_dir must be disjoint; parent/child overlap is unsafe.",
                    "Choose a data directory outside the game installation tree.",
                )
            )

    if game_root is not None:
        exists = _safe_exists(
            game_root,
            diagnostics,
            code="GAME_ROOT_INACCESSIBLE",
            label="Configured game_root",
        )
        if exists is False:
            diagnostics.append(
                Diagnostic("GAME_ROOT_MISSING", "error", "Configured game_root does not exist.")
            )
        elif exists is True:
            try:
                is_dir = game_root.is_dir()
            except _PATH_ERRORS:
                is_dir = False
                diagnostics.append(
                    Diagnostic("GAME_ROOT_INACCESSIBLE", "error", "Configured game_root cannot be inspected.")
                )
            if not is_dir:
                diagnostics.append(
                    Diagnostic("GAME_ROOT_NOT_DIRECTORY", "error", "Configured game_root is not a directory.")
                )
            else:
                mode = os.R_OK | (os.X_OK if os.name == "posix" else 0)
                try:
                    accessible = access_checker(game_root, mode)
                except _PATH_ERRORS:
                    accessible = False
                if not accessible:
                    diagnostics.append(
                        Diagnostic(
                            "GAME_ROOT_UNREADABLE",
                            "error",
                            "Configured game_root is not readable/traversable.",
                        )
                    )

    data_exists = _safe_exists(
        data_dir,
        diagnostics,
        code="DATA_DIR_INACCESSIBLE",
        label="Configured data_dir",
    )
    if data_exists is False:
        diagnostics.append(
            Diagnostic(
                "DATA_DIR_MISSING",
                "error",
                "Configured data_dir does not exist.",
                "Create the private data directory outside the game tree.",
            )
        )
    elif data_exists is True:
        try:
            is_dir = data_dir.is_dir()
        except _PATH_ERRORS:
            is_dir = False
            diagnostics.append(
                Diagnostic("DATA_DIR_INACCESSIBLE", "error", "Configured data_dir cannot be inspected.")
            )
        if not is_dir:
            diagnostics.append(
                Diagnostic("DATA_DIR_NOT_DIRECTORY", "error", "Configured data_dir is not a directory.")
            )
        else:
            mode = os.R_OK | os.W_OK | (os.X_OK if os.name == "posix" else 0)
            try:
                accessible = access_checker(data_dir, mode)
            except _PATH_ERRORS:
                accessible = False
            if not accessible:
                diagnostics.append(
                    Diagnostic(
                        "DATA_DIR_NOT_WRITABLE",
                        "error",
                        "Configured data_dir is not readable/writable/traversable.",
                    )
                )
    return tuple(diagnostics)
