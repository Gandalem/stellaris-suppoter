from __future__ import annotations

import os
from pathlib import Path

from stellaris_supporter.config import (
    default_config_path,
    default_data_dir,
    load_settings,
    paths_overlap,
    validate_paths,
)


def codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


def write_config(path: Path, game: str = "game", data: str = "data", extra: str = "") -> None:
    path.write_text(
        (
            "schema_version = 1\n"
            f'game_root = "{game}"\n'
            f'data_dir = "{data}"\n'
            'language = "ko"\n'
            "[network]\n"
            "enabled = false\n"
            + extra
        ),
        encoding="utf-8",
    )


def test_relative_toml_paths_resolve_from_config_directory(tmp_path: Path) -> None:
    game = tmp_path / "game"
    data = tmp_path / "data"
    game.mkdir()
    data.mkdir()
    config = tmp_path / "settings.toml"
    write_config(config)
    result = load_settings(config)
    assert result.settings.game_root == game.resolve()
    assert result.settings.data_dir == data.resolve()
    assert not {d.code for d in validate_paths(result.settings) if d.severity == "error"}


def test_cli_override_precedes_toml_and_uses_cwd(tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    cwd = tmp_path / "work"
    config_dir.mkdir()
    cwd.mkdir()
    (config_dir / "game").mkdir()
    (config_dir / "data").mkdir()
    (cwd / "override-game").mkdir()
    config = config_dir / "settings.toml"
    write_config(config)
    result = load_settings(config, overrides={"game_root": "override-game"}, cwd=cwd)
    assert result.settings.game_root == (cwd / "override-game").resolve()


def test_missing_malformed_and_unreadable_config_are_structured(tmp_path: Path) -> None:
    missing = load_settings(tmp_path / "missing.toml")
    assert "CONFIG_MISSING" in codes(missing)
    malformed = tmp_path / "broken.toml"
    malformed.write_text("game_root = [", encoding="utf-8")
    assert "CONFIG_INVALID_TOML" in codes(load_settings(malformed))
    config = tmp_path / "settings.toml"
    config.write_text("schema_version = 1\n", encoding="utf-8")
    def denied(_: Path) -> bytes:
        raise PermissionError("synthetic denial")
    unreadable = load_settings(config, reader=denied)
    assert "CONFIG_UNREADABLE" in codes(unreadable)


def test_unknown_key_bad_limit_and_network_true_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text(
        "schema_version = 1\n"
        'game_root = "game"\n'
        'data_dir = "data"\n'
        "mystery = 1\n"
        "[network]\n"
        "enabled = true\n"
        "[limits]\n"
        "max_depth = 0\n",
        encoding="utf-8",
    )
    result = load_settings(config)
    assert {"CONFIG_UNKNOWN_KEY", "NETWORK_REJECTED", "CONFIG_INVALID_LIMIT"} <= codes(result)
    assert result.settings.network_enabled is False


def test_game_root_is_never_read_from_environment(tmp_path: Path) -> None:
    result = load_settings(
        None,
        system="Linux",
        env={"STELLARIS_GAME_ROOT": str(tmp_path / "secret")},
        home=tmp_path,
    )
    assert result.settings.game_root is None
    assert "GAME_ROOT_REQUIRED" in codes(result)


def test_default_paths_are_platform_specific(tmp_path: Path) -> None:
    win_env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    assert default_config_path(system="Windows", env=win_env, home=tmp_path) == (
        tmp_path / "Local" / "StellarisSupporter" / "config.toml"
    )
    assert default_data_dir(system="Windows", env=win_env, home=tmp_path) == (
        tmp_path / "Local" / "StellarisSupporter" / "data"
    )
    assert default_config_path(system="Linux", env={}, home=tmp_path) == (
        tmp_path / ".config" / "stellaris-supporter" / "config.toml"
    )


def test_overlap_and_access_failures_are_reported(tmp_path: Path) -> None:
    game = tmp_path / "game"
    data = tmp_path / "data"
    game.mkdir()
    data.mkdir()
    assert paths_overlap(game, game / "child")
    assert paths_overlap(game, tmp_path)
    config = tmp_path / "settings.toml"
    write_config(config)
    settings = load_settings(config).settings
    denied = {item.code for item in validate_paths(settings, access_checker=lambda _p, _m: False)}
    assert {"GAME_ROOT_UNREADABLE", "DATA_DIR_NOT_WRITABLE"} <= denied
    data.rmdir()
    assert "DATA_DIR_MISSING" in {item.code for item in validate_paths(settings)}


def test_game_root_access_check_never_requests_write(tmp_path: Path) -> None:
    game = tmp_path / "game"
    data = tmp_path / "data"
    game.mkdir()
    data.mkdir()
    config = tmp_path / "settings.toml"
    write_config(config)
    seen: list[tuple[Path, int]] = []
    def record(path: Path, mode: int) -> bool:
        seen.append((path, mode))
        return True
    validate_paths(load_settings(config).settings, access_checker=record)
    assert (game.resolve(), os.R_OK) in seen
    assert (data.resolve(), os.R_OK | os.W_OK) in seen
