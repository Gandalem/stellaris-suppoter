from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from stellaris_supporter.cli import main
from stellaris_supporter.config import load_settings
from stellaris_supporter.doctor import run_doctor


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def make_config(tmp_path: Path, *, data_inside_game: bool = False) -> Path:
    game = tmp_path / "game"
    game.mkdir()
    data = game / "data" if data_inside_game else tmp_path / "data"
    data.mkdir()
    config = tmp_path / "settings.toml"
    config.write_text(
        "schema_version = 1\n"
        f'game_root = "{game.as_posix()}"\n'
        f'data_dir = "{data.as_posix()}"\n'
        'language = "ko"\n'
        "[network]\n"
        "enabled = false\n",
        encoding="utf-8",
    )
    return config


def test_doctor_reports_runtime_and_fts_fallback(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    report = run_doctor(load_settings(config), fts_probe=lambda: False)
    assert report.exit_code == 0
    assert report.status == "warning"
    assert report.runtime.application_version == "0.0.1"
    assert report.runtime.fts5_available is False
    codes = {item.code for item in report.diagnostics}
    assert {"SQLITE_FTS5_UNAVAILABLE", "NETWORK_DISABLED"} <= codes


def test_public_report_redacts_absolute_paths(tmp_path: Path) -> None:
    report = run_doctor(load_settings(make_config(tmp_path)))
    payload = report.to_dict(public=True)
    assert payload["settings"]["config_path"] == "<CONFIG_PATH>"
    assert payload["settings"]["game_root"] == "<GAME_ROOT>"
    assert payload["settings"]["data_dir"] == "<DATA_DIR>"


def test_doctor_overlap_is_safety_exit_four(tmp_path: Path) -> None:
    config = make_config(tmp_path, data_inside_game=True)
    result = run_module("--format", "json", "--config", str(config), "doctor")
    payload = json.loads(result.stdout)
    assert result.returncode == 4
    assert payload["status"] == "error"
    assert any(item["code"] == "PATH_REJECTED" for item in payload["diagnostics"])


def test_doctor_json_is_single_object_with_capabilities(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    result = run_module("--format", "json", "--config", str(config), "doctor")
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert result.stderr == ""
    assert payload["schema_version"] == 1
    assert payload["settings"]["network_enabled"] is False
    assert payload["runtime"]["application_version"] == "0.0.1"
    assert isinstance(payload["runtime"]["fts5_available"], bool)
    assert payload["settings"]["game_root"] == str((tmp_path / "game").resolve())


def test_doctor_missing_config_is_exit_three(tmp_path: Path) -> None:
    result = run_module("--format", "json", "--config", str(tmp_path / "none.toml"), "doctor")
    payload = json.loads(result.stdout)
    assert result.returncode == 3
    codes = {item["code"] for item in payload["diagnostics"]}
    assert {"CONFIG_MISSING", "GAME_ROOT_REQUIRED"} <= codes


def test_public_report_redacts_paths_from_entire_payload(tmp_path: Path) -> None:
    secret = str((tmp_path / "secret").resolve())
    config = tmp_path / "settings.toml"
    config.write_text(
        "schema_version = 1\n"
        f'"{secret}" = 1\n'
        'game_root = "game"\n'
        'data_dir = "data"\n',
        encoding="utf-8",
    )
    report = run_doctor(load_settings(config))
    encoded = json.dumps(report.to_dict(public=True), ensure_ascii=False)
    assert secret not in encoded


def test_doctor_invalid_nul_config_path_returns_json_not_traceback(capsys) -> None:
    exit_code = main(["--format", "json", "--config", "bad\x00path", "doctor"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 3
    assert payload["status"] == "error"
    assert captured.err == ""
    assert any(
        item["code"] in {"CONFIG_PATH_INVALID", "CONFIG_PATH_INACCESSIBLE"}
        for item in payload["diagnostics"]
    )
