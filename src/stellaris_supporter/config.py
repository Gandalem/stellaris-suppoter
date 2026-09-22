"""Configuration loading and path policy."""

from __future__ import annotations

import os
import platform
import re
import stat
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
StatReader = Callable[[Path], os.stat_result]


def _env_absolute_or_default(
    environment: Mapping[str, str],
    key: str,
    default: Path,
) -> Path:
    raw = environment.get(key)
    if not raw:
        return default
    try:
        candidate = Path(raw)
    except (TypeError, ValueError):
        return default
    return candidate if candidate.is_absolute() else default


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
        base = _env_absolute_or_default(
            environment,
            "LOCALAPPDATA",
            home_dir / "AppData" / "Local",
        )
        return base / "StellarisSupporter" / "config.toml"
    if system_name == "darwin":
        return home_dir / "Library" / "Application Support" / "StellarisSupporter" / "config.toml"

    base = _env_absolute_or_default(
        environment,
        "XDG_CONFIG_HOME",
        home_dir / ".config",
    )
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
        base = _env_absolute_or_default(
            environment,
            "LOCALAPPDATA",
            home_dir / "AppData" / "Local",
        )
        return base / "StellarisSupporter" / "data"
    if system_name == "darwin":
        return home_dir / "Library" / "Application Support" / "StellarisSupporter" / "data"

    base = _env_absolute_or_default(
        environment,
        "XDG_DATA_HOME",
        home_dir / ".local" / "share",
    )
    return base / "stellaris-supporter"


def _default_reader(path: Path) -> bytes:
    return path.read_bytes()


def _default_stat_reader(path: Path) -> os.stat_result:
    return path.stat()


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

    if set(parsed) - _ALLOWED_TOP_LEVEL:
        diagnostics.append(
            Diagnostic(
                "CONFIG_UNKNOWN_KEY",
                "error",
                "Configuration contains unsupported top-level key(s).",
                "Remove unsupported or misspelled keys.",
            )
        )

    network = parsed.get("network", {})
    if not isinstance(network, dict):
        diagnostics.append(
            Diagnostic("CONFIG_INVALID_TYPE", "error", "[network] must be a TOML table.")
        )
    elif set(network) - _ALLOWED_NETWORK:
        diagnostics.append(
            Diagnostic(
                "CONFIG_UNKNOWN_KEY",
                "error",
                "Configuration contains unsupported [network] key(s).",
            )
        )

    limits = parsed.get("limits", {})
    if not isinstance(limits, dict):
        diagnostics.append(
            Diagnostic("CONFIG_INVALID_TYPE", "error", "[limits] must be a TOML table.")
        )
    elif set(limits) - _ALLOWED_LIMITS:
        diagnostics.append(
            Diagnostic(
                "CONFIG_UNKNOWN_KEY",
                "error",
                "Configuration contains unsupported [limits] key(s).",
            )
        )
    return diagnostics


def _resolve_user_path(
    value: str | Path,
    *,
    base: Path,
    code: str,
    label: str,
    diagnostics: list[Diagnostic],
) -> Path | None:
    try:
        raw = os.fspath(value)
        if "\x00" in raw:
            raise ValueError("NUL is not allowed in filesystem paths")
        path = Path(raw).expanduser()
        if raw.startswith("~") and str(path).startswith("~"):
            raise RuntimeError("home expression could not be resolved")
        if not path.is_absolute():
            path = base / path
        return path.resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError):
        diagnostics.append(
            Diagnostic(
                code,
                "error",
                f"{label} is not a valid or resolvable filesystem path.",
                "Use an explicit accessible filesystem path.",
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
            Diagnostic(
                "CONFIG_INVALID_LIMIT",
                "error",
                f"limits.{key} must be a positive integer.",
            )
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
    diagnostics: list[Diagnostic] = []
    environment = env if env is not None else os.environ

    try:
        current_dir = (cwd if cwd is not None else Path.cwd()).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        current_dir = home if home is not None else Path.home()
        diagnostics.append(
            Diagnostic(
                "CONFIG_CWD_INVALID",
                "error",
                "Current working directory cannot be resolved safely.",
            )
        )

    explicit_config = config_path is not None
    selected_raw = config_path or default_config_path(
        system=system,
        env=environment,
        home=home,
    )
    selected_config = _resolve_user_path(
        selected_raw,
        base=current_dir,
        code="CONFIG_PATH_INVALID",
        label="Configuration path",
        diagnostics=diagnostics,
    )
    config_path_valid = selected_config is not None
    if selected_config is None:
        selected_config = current_dir / ".invalid-stellaris-supporter-config"

    parsed: dict[str, Any] = {}
    if config_path_valid:
        try:
            data = reader(selected_config)
        except FileNotFoundError:
            diagnostics.append(
                Diagnostic(
                    "CONFIG_MISSING" if explicit_config else "CONFIG_DEFAULT_MISSING",
                    "error" if explicit_config else "info",
                    (
                        "The explicitly selected configuration file does not exist."
                        if explicit_config
                        else "No default configuration file was found; CLI values and safe defaults are in use."
                    ),
                    (
                        "Create the file or pass a different --config path."
                        if explicit_config
                        else None
                    ),
                )
            )
        except (OSError, ValueError):
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

    schema_version = parsed.get("schema_version", 1)
    if type(schema_version) is not int or schema_version != 1:
        diagnostics.append(
            Diagnostic(
                "CONFIG_SCHEMA_UNSUPPORTED",
                "error",
                "schema_version must be integer 1.",
            )
        )

    cli = dict(overrides or {})
    config_base = selected_config.parent

    def choose_path(name: str) -> Path | None:
        override = cli.get(name)
        if override is not None:
            if not isinstance(override, str) or not override.strip():
                diagnostics.append(
                    Diagnostic(
                        "CONFIG_INVALID_TYPE",
                        "error",
                        f"{name} override must be a path string.",
                    )
                )
                return None
            return _resolve_user_path(
                override,
                base=current_dir,
                code=f"{name.upper()}_INVALID_PATH",
                label=name,
                diagnostics=diagnostics,
            )

        value = parsed.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            diagnostics.append(
                Diagnostic(
                    "CONFIG_INVALID_TYPE",
                    "error",
                    f"{name} must be a non-empty path string.",
                )
            )
            return None
        return _resolve_user_path(
            value,
            base=config_base,
            code=f"{name.upper()}_INVALID_PATH",
            label=name,
            diagnostics=diagnostics,
        )

    game_path_was_supplied = cli.get("game_root") is not None or parsed.get("game_root") is not None
    game_root = choose_path("game_root")
    if game_root is None and not game_path_was_supplied:
        diagnostics.append(
            Diagnostic(
                "GAME_ROOT_REQUIRED",
                "error",
                "game_root is not configured; automatic game discovery is disabled.",
                "Set game_root in TOML or pass --game-root explicitly.",
            )
        )

    data_path_was_supplied = cli.get("data_dir") is not None or parsed.get("data_dir") is not None
    data_dir = choose_path("data_dir")
    if data_dir is None:
        default_data = default_data_dir(system=system, env=environment, home=home)
        resolved_default = _resolve_user_path(
            default_data,
            base=current_dir,
            code="DATA_DIR_DEFAULT_INVALID",
            label="Default data directory",
            diagnostics=diagnostics,
        )
        data_dir = resolved_default or (current_dir / ".stellaris-supporter-data")
        if data_path_was_supplied:
            diagnostics.append(
                Diagnostic(
                    "DATA_DIR_FALLBACK",
                    "info",
                    "Invalid configured data_dir was not used; safe default selected for diagnostics.",
                )
            )

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
                Diagnostic(
                    "CONFIG_INVALID_TYPE",
                    "error",
                    "network.enabled must be true or false.",
                )
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

    return ConfigResult(
        Settings(
            config_path=selected_config,
            game_root=game_root,
            data_dir=data_dir,
            language=language,
            network_enabled=False,
            limits=limits,
        ),
        tuple(diagnostics),
    )


def paths_overlap(first: Path, second: Path) -> bool:
    try:
        first_resolved = first.resolve(strict=False)
        second_resolved = second.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        first_resolved == second_resolved
        or first_resolved in second_resolved.parents
        or second_resolved in first_resolved.parents
    )


def _validate_directory(
    path: Path,
    *,
    missing_code: str,
    not_directory_code: str,
    inaccessible_code: str,
    inaccessible_message: str,
    access_mode: int,
    access_checker: AccessChecker,
    stat_reader: StatReader,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    try:
        info = stat_reader(path)
    except FileNotFoundError:
        diagnostics.append(Diagnostic(missing_code, "error", "Configured directory does not exist."))
        return diagnostics
    except (OSError, ValueError):
        diagnostics.append(
            Diagnostic(
                inaccessible_code,
                "error",
                "Configured directory metadata cannot be accessed.",
            )
        )
        return diagnostics

    if not stat.S_ISDIR(info.st_mode):
        diagnostics.append(
            Diagnostic(not_directory_code, "error", "Configured path is not a directory.")
        )
        return diagnostics

    try:
        allowed = access_checker(path, access_mode)
    except (OSError, ValueError):
        allowed = False
    if not allowed:
        diagnostics.append(
            Diagnostic(
                inaccessible_code,
                "error",
                inaccessible_message,
            )
        )
    return diagnostics


def validate_paths(
    settings: Settings,
    *,
    access_checker: AccessChecker = os.access,
    stat_reader: StatReader = _default_stat_reader,
    platform_name: str | None = None,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    game_root = settings.game_root
    data_dir = settings.data_dir

    if game_root is not None:
        try:
            overlap = paths_overlap(game_root, data_dir)
        except (OSError, RuntimeError, ValueError):
            overlap = False
            diagnostics.append(
                Diagnostic(
                    "PATH_INVALID",
                    "error",
                    "Configured paths cannot be compared safely.",
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

    is_posix = (os.name == "posix") if platform_name is None else platform_name == "posix"
    traverse = os.X_OK if is_posix else 0

    if game_root is not None:
        diagnostics.extend(
            _validate_directory(
                game_root,
                missing_code="GAME_ROOT_MISSING",
                not_directory_code="GAME_ROOT_NOT_DIRECTORY",
                inaccessible_code="GAME_ROOT_UNREADABLE",
                inaccessible_message=(
                    "Configured game_root is not readable/traversable for required source access."
                ),
                access_mode=os.R_OK | traverse,
                access_checker=access_checker,
                stat_reader=stat_reader,
            )
        )

    diagnostics.extend(
        _validate_directory(
            data_dir,
            missing_code="DATA_DIR_MISSING",
            not_directory_code="DATA_DIR_NOT_DIRECTORY",
            inaccessible_code="DATA_DIR_NOT_WRITABLE",
            inaccessible_message=(
                "Configured data_dir is not readable, writable, and traversable as required."
            ),
            access_mode=os.R_OK | os.W_OK | traverse,
            access_checker=access_checker,
            stat_reader=stat_reader,
        )
    )
    return tuple(diagnostics)
