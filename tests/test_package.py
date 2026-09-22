from __future__ import annotations

import subprocess
import sys

import stellaris_supporter


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_package_import_exposes_installed_version() -> None:
    assert stellaris_supporter.__version__ == "0.0.1"


def test_module_help_succeeds_without_advertising_future_commands() -> None:
    result = run_module("--help")

    assert result.returncode == 0
    assert "project scaffold" in result.stdout
    for future_command in ("index", "search", "show", "refs", "snapshots", "diff"):
        assert future_command not in result.stdout


def test_module_version_succeeds() -> None:
    result = run_module("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == "stellaris-supporter 0.0.1"


def test_no_argument_invocation_is_safe_and_informative() -> None:
    result = run_module()

    assert result.returncode == 0
    assert "usage: stellaris-supporter" in result.stdout
    assert result.stderr == ""
