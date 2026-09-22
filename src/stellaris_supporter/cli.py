"""Command-line entry point for the package scaffold."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from stellaris_supporter import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the TASK-001 scaffold parser without advertising future features."""
    parser = argparse.ArgumentParser(
        prog="stellaris-supporter",
        description=(
            "Stellaris Supporter project scaffold. "
            "Game indexing, search, and analysis commands are not implemented yet."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scaffold CLI."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
