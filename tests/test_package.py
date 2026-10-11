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


def test_module_help_advertises_implemented_product_commands_only() -> None:
    result = run_module("--help")
    assert result.returncode == 0
    assert "{init,doctor,index,search,show,snapshots}" in result.stdout
    assert "refs" not in result.stdout
    assert "diff" not in result.stdout


def test_module_version_succeeds() -> None:
    result = run_module("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == "stellaris-supporter 0.0.1"


def test_no_argument_invocation_is_safe_and_informative() -> None:
    result = run_module()
    assert result.returncode == 0
    assert "usage: stellaris-supporter" in result.stdout
    assert "doctor" in result.stdout
    assert result.stderr == ""
