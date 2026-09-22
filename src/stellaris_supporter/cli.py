"""Command-line entry point for implemented Stellaris Supporter features."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from stellaris_supporter import __version__
from stellaris_supporter.config import load_settings
from stellaris_supporter.doctor import DoctorReport, run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stellaris-supporter",
        description="Local-first Stellaris data assistant under incremental development.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="TOML configuration path.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--game-root", help="Explicit game root override; no auto-discovery.")
    parser.add_argument("--data-dir", help="Explicit private data directory override.")
    parser.add_argument("--language", help="Language code override, for example ko or en.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "doctor",
        help="Validate configuration, paths, and local runtime capabilities.",
    )
    return parser


def _format_doctor_text(report: DoctorReport) -> str:
    settings = report.settings
    runtime = report.runtime
    lines = [
        f"status: {report.status}",
        f"config: {settings['config_path']}",
        f"game_root: {settings['game_root']}",
        f"data_dir: {settings['data_dir']}",
        f"language: {settings['language']}",
        f"network_enabled: {str(settings['network_enabled']).lower()}",
        f"application_version: {runtime.application_version}",
        f"python_version: {runtime.python_version}",
        f"sqlite_version: {runtime.sqlite_version}",
        f"fts5_available: {str(runtime.fts5_available).lower()}",
        "diagnostics:",
    ]
    for item in report.diagnostics:
        line = f"- {item.severity} {item.code}: {item.message}"
        if item.remediation:
            line += f" remediation={item.remediation}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _doctor_from_args(args: argparse.Namespace) -> int:
    result = load_settings(
        args.config,
        overrides={
            "game_root": args.game_root,
            "data_dir": args.data_dir,
            "language": args.language,
        },
    )
    report = run_doctor(result)
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(_format_doctor_text(report), end="")
    return report.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor_from_args(args)
    parser.print_help()
    return 0
