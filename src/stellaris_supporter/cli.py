"""Deterministic offline technology CLI. All facts come from existing services."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from stellaris_supporter import __version__
from stellaris_supporter.answers import AnswerService
from stellaris_supporter.cli_index import _language, index_technologies
from stellaris_supporter.cli_setup import _check_components, initialise_config
from stellaris_supporter.config import default_config_path, load_settings, validate_paths
from stellaris_supporter.doctor import DoctorReport, run_doctor
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository


class _UsageError(ValueError):
    """Sanitized argparse failure without a raw command-line echo."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError("Invalid command arguments.") from None


def _wants_json(argv: Sequence[str] | None) -> bool:
    selected = list(sys.argv[1:] if argv is None else argv)
    return any(
        (arg == "--format" and index + 1 < len(selected)
         and selected[index + 1] == "json") or arg == "--format=json"
        for index, arg in enumerate(selected)
    )


def _add_common(parser: argparse.ArgumentParser, *, subcommand: bool = False) -> None:
    # SUPPRESS prevents absent subcommand options from erasing global values.
    kw = {"default": argparse.SUPPRESS} if subcommand else {}
    parser.add_argument("--config", type=Path, help="TOML configuration path.", **kw)
    parser.add_argument("--format", choices=("text", "json"),
                        help="Output format.", **({**kw, "default": "text"} if not subcommand else kw))
    parser.add_argument("--game-root", help="Explicit game root; never discovered.", **kw)
    parser.add_argument("--data-dir", help="Private data directory.", **kw)
    parser.add_argument("--language", help="ko/en or korean/english.", **kw)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="stellaris-supporter",
        description="Offline technology indexing, search, and verified static citations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_common(parser)
    sub = parser.add_subparsers(dest="command")
    init = sub.add_parser("init", help="Create private, offline TOML configuration once.")
    _add_common(init, subcommand=True)
    doctor = sub.add_parser("doctor", help="Inspect configuration and local runtime only.")
    _add_common(doctor, subcommand=True)
    index = sub.add_parser("index", help="Safely index technology and Korean/English localisation.")
    _add_common(index, subcommand=True)
    index.add_argument("--allow-partial", action="store_true",
                       help="Explicitly activate parsed-but-partial snapshot; never bypass security.")
    index.add_argument("--include-events", action="store_true",
                       help="Also index supported literal event references.")
    index.add_argument("--full", action="store_true", help="Parse all files without product reuse.")
    search = sub.add_parser("search", help="Search IDs and Korean/English names.")
    _add_common(search, subcommand=True)
    search.add_argument("text")
    search.add_argument("--kind", default=None)
    search.add_argument("--snapshot", default=None)
    search.add_argument("--limit", type=int, default=None)
    show = sub.add_parser("show", help="Show verified facts for an exact game ID.")
    _add_common(show, subcommand=True)
    show.add_argument("game_id")
    show.add_argument("--kind", default="technology")
    show.add_argument("--snapshot", default=None)
    show.add_argument("--limit", type=int, default=None)
    refs = sub.add_parser("refs", help="Trace exact technology prerequisites or literal event calls.")
    _add_common(refs, subcommand=True)
    refs.add_argument("game_id")
    refs.add_argument("--kind", default="technology", choices=("technology", "event"))
    refs.add_argument("--snapshot", default=None)
    refs.add_argument("--entity-key", default=None)
    refs.add_argument("--depth", type=int, default=1)
    refs.add_argument("--limit", type=int, default=None)
    diff = sub.add_parser("diff", help="Compare immutable snapshot definitions, references and translations.")
    _add_common(diff, subcommand=True)
    diff.add_argument("before_snapshot")
    diff.add_argument("after_snapshot")
    diff.add_argument("--kind", choices=("technology", "event"), default=None)
    diff.add_argument("--game-id", default=None)
    diff.add_argument("--include-source-changes", action="store_true")
    diff.add_argument("--limit", type=int, default=None)
    diff.add_argument("--offset", type=int, default=0)
    snaps = sub.add_parser("snapshots", help="List snapshot statuses and active pointer.")
    _add_common(snaps, subcommand=True)
    snaps.add_argument("--limit", type=int, default=100)
    snaps.add_argument("--offset", type=int, default=0)
    return parser


MAX_CLI_OUTPUT_BYTES = 1024 * 1024


def _bounded_json(payload: dict) -> str:
    """Serialize one complete JSON object without unbounded output buffering.

    The wire representation, not only number of facts, is capped. Any
    over-budget response is fully abstained, not returned as partial facts.
    """
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, allow_nan=False)
    parts: list[str] = []
    total = 0
    for fragment in encoder.iterencode(payload):
        total += len(fragment.encode("utf-8"))
        if total > MAX_CLI_OUTPUT_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "CLI output byte budget exceeded.")
        parts.append(fragment)
    return "".join(parts)


def _safe_terminal_line(line: str) -> str:
    """Escape all nonprinting control/format characters on human text only."""
    pieces: list[str] = []
    for character in line:
        if character.isprintable():
            pieces.append(character)
        elif character == "\r":
            pieces.append("\\r")
        elif character == "\b":
            pieces.append("\\b")
        elif character == "\n":
            pieces.append("\\n")
        elif character == "\t":
            pieces.append("\\t")
        else:
            code = ord(character)
            if code <= 0xFF:
                pieces.append(f"\\x{code:02x}")
            elif code <= 0xFFFF:
                pieces.append(f"\\u{code:04x}")
            else:
                pieces.append(f"\\U{code:08x}")
    return "".join(pieces)


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
    return "\n".join(_safe_terminal_line(line) for line in lines) + "\n"


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


def _code_exit(code: str) -> int:
    if code in {"QUERY_INVALID", "CONFIG_INVALID_LANGUAGE"}:
        return 2
    if code in {
        "CONFIG_MISSING", "CONFIG_DEFAULT_MISSING", "GAME_ROOT_REQUIRED",
        "GAME_ROOT_MISSING", "SNAPSHOT_MISSING", "SNAPSHOT_NOT_FOUND",
        "SNAPSHOT_NOT_READY",
        "FILESYSTEM_ERROR", "CONFIG_UNREADABLE", "DATA_DIR_MISSING",
    }:
        return 3
    if code in {
        "CONFIG_EXISTS", "PATH_REJECTED", "LIMIT_EXCEEDED",
        "NETWORK_REJECTED", "SOURCE_UNVERIFIED", "COLLISION_UNRESOLVED",
    }:
        return 4
    if code in {
        "SOURCE_CHANGED", "PARTIAL_INDEX", "ADAPTER_PARSE_ERROR",
        "ENCODING_ERROR", "PARSER_INVALID",
    }:
        return 5
    if code == "CANCELLED":
        return 130
    if code.startswith(("CONFIG_", "GAME_ROOT_", "DATA_DIR_", "CWD_")):
        return 3
    if code in {"PATH_INVALID", "SNAPSHOT_NOT_READY", "FILESYSTEM_ERROR"}:
        return 3
    return 6


def _failed(command: str | None, code: str, *, exit_code: int | None = None) -> tuple[int, dict]:
    return (
        _code_exit(code) if exit_code is None else exit_code,
        {"schema_version": 1, "command": command,
         "status": "error", "results": [],
         "diagnostics": [{"code": code, "severity": "error",
                          "message": f"Request failed: {code}."}]},
    )


def _emit_text(payload: dict) -> None:
    if payload.get("command") == "diff":
        query = payload.get("query") or {}
        lines = ["command: diff", f"status: {payload.get('status')}",
                 f"before: {query.get('before_snapshot', 'unknown')}",
                 f"after: {query.get('after_snapshot', 'unknown')}",
                 f"summary_complete: {payload.get('summary_complete', False)}",
                 "summary: " + json.dumps(payload.get("summary", {}), ensure_ascii=False, sort_keys=True)]
        for item in payload.get("results", []):
            lines.append(f"- {item['change_kind']} {item['kind']} {item['game_id']}")
            for side in ("before", "after"):
                value = item.get(side)
                if isinstance(value, dict):
                    ref = value.get("source_ref")
                    if ref:
                        lines.append(f"  {side}: {ref['relative_path']}:{ref['line_start']}-{ref['line_end']}")
            for detail in item.get("details", []):
                lines.append(f"  {detail.get('field', detail['section'])}: "
                             + json.dumps(detail.get("before"), ensure_ascii=False)
                             + " -> " + json.dumps(detail.get("after"), ensure_ascii=False))
        for diagnostic in payload.get("diagnostics", []):
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
        if payload.get("truncated"):
            lines.append("truncated: " + ", ".join(payload.get("truncation_reasons", [])))
        print("\n".join(_safe_terminal_line(line) for line in lines))
        return
    if payload.get("command") == "refs":
        lines = ["command: refs", f"status: {payload.get('status')}",
                 f"snapshot: {payload.get('snapshot_id') or 'unknown'}"]
        if payload.get("truncated"):
            lines.append("truncated: " + ", ".join(payload.get("truncation_reasons", [])))
        for node in (*payload.get("candidates", []), *payload.get("nodes", [])):
            ref = node["source_ref"]
            lines.append(f"- {node['game_id']} key={node['entity_key']} depth={node['depth']} "
                         f"[{ref['relative_path']}:{ref['line_start']}-{ref['line_end']}]")
        for edge in payload.get("edges", []):
            ref = edge["source_ref"]
            lines.append(f"  {edge['from_entity_key']} -> {edge['target_game_id']} "
                         f"({edge['status']}, occurrence={edge['occurrence']}) "
                         f"[{ref['relative_path']}:{ref['line_start']}-{ref['line_end']}]")
        for cycle in payload.get("cycles", []):
            lines.append("cycle: " + " -> ".join(cycle))
        for diagnostic in payload.get("diagnostics", []):
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
        print("\n".join(_safe_terminal_line(line) for line in lines))
        return
    if payload.get("command") == "snapshots":
        lines = [
            "command: snapshots", f"status: {payload.get('status')}",
            f"limit: {payload.get('limit', 100)}",
            f"offset: {payload.get('offset', 0)}",
            f"truncated: {str(bool(payload.get('truncated'))).lower()}",
        ]
        for item in payload.get("results", []):
            lines.append(f"- snapshot_id: {item['snapshot_id']}")
            for key in ("active", "status", "context_kind", "branch",
                        "game_version", "created_at", "checked_at"):
                value = item.get(key)
                if isinstance(value, bool):
                    value = str(value).lower()
                elif value is None:
                    value = "unknown"
                lines.append(f"  {key}: {value}")
        for diagnostic in payload.get("diagnostics", []):
            lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
        print("\n".join(_safe_terminal_line(line) for line in lines))
        return
    context = payload.get("context") or {}
    lines = [f"command: {payload.get('command')}",
             f"status: {payload.get('status')}",
             f"snapshot: {payload.get('snapshot_id') or context.get('snapshot_id') or 'unknown'}",
             f"version: {context.get('game_version') or payload.get('game_version') or 'unknown'}",
             f"context_kind: {context.get('context_kind') or payload.get('context_kind') or 'unknown'}",
             f"branch: {context.get('branch') or payload.get('branch') or 'unknown'}"]
    if payload.get("processing"):
        lines.append("processing: " + json.dumps(payload["processing"], ensure_ascii=False, sort_keys=True))
    if payload.get("reused") is not None:
        lines.append(f"reused: {str(payload['reused']).lower()}")
    if payload.get("activated") is not None:
        lines.append(f"activated: {str(payload['activated']).lower()}")
    if payload.get("truncated"):
        lines.append("truncated: true")
    for hit in payload.get("results", []):
        lines.append(f"- {hit.get('game_id', hit.get('snapshot_id', ''))} "
                     f"{hit.get('display_name', '')} ({hit.get('status', '')})")
        if hit.get("fallback") is not None:
            lines.append(f"  fallback: {hit['fallback']}")
        definition = hit.get("definition_source_ref")
        if definition is not None:
            lines.append(
                f"  definition: {definition['relative_path']}:"
                f"{definition['line_start']}-{definition['line_end']}"
            )
        for item in hit.get("facts", []):
            span = item["value_source_ref"] or item["source_ref"]
            lines.append(f"  {item['field_name']} = {item['raw_expression']!r} "
                         f"[{span['relative_path']}:{span['line_start']}-{span['line_end']}] "
                         f"({item['support_status']})")
    for diagnostic in payload.get("diagnostics", []):
        lines.append(f"- {diagnostic['code']}: {diagnostic['message']}")
    print("\n".join(_safe_terminal_line(line) for line in lines))


def _guard_original_config_paths(args: argparse.Namespace) -> None:
    """Reject path links *before* load_settings resolves lexical spellings."""
    selected = args.config or default_config_path()
    _check_components(selected)
    for raw in (args.game_root, args.data_dir):
        if raw is not None:
            _check_components(Path(raw))
    try:
        if not selected.is_file():
            return  # Existing loader will produce CONFIG_MISSING.
        # Bounded, read-only inspection; the loader still owns all TOML validation.
        if selected.stat().st_size > 1024 * 1024:
            raise SnapshotError("LIMIT_EXCEEDED", "Configuration file too large.")
        with selected.open("rb") as stream:
            data = tomllib.load(stream)
        for name in ("game_root", "data_dir"):
            if getattr(args, name) is not None:
                continue
            raw = data.get(name)
            if not isinstance(raw, str):
                continue
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = selected.parent / path
            _check_components(path)
    except (tomllib.TOMLDecodeError, UnicodeError, ValueError):
        # Preserve the loader's existing typed CONFIG_INVALID diagnostics.
        return
    except OSError as exc:
        raise SnapshotError("CONFIG_UNREADABLE", "Configuration path cannot be inspected.") from exc


def _load_checked(args: argparse.Namespace):
    _guard_original_config_paths(args)
    config = load_settings(
        args.config,
        overrides={"game_root": args.game_root,
                   "data_dir": args.data_dir,
                   "language": args.language},
    )
    errors = [d for d in (*config.diagnostics, *validate_paths(config.settings))
              if d.severity == "error"]
    if errors:
        code = next((d.code for d in errors if _code_exit(d.code) == 4), errors[0].code)
        raise SnapshotError(code, "Configuration or path validation failed.")
    _language(config.settings.language)
    return config.settings


def _response_code(payload: dict) -> int:
    if payload["status"] != "error":
        return 0
    diagnostics = payload.get("diagnostics") or []
    code = diagnostics[0].get("code", "SQLITE_ERROR") if diagnostics else "SQLITE_ERROR"
    return _code_exit(code)


def _bounded_query_limit(text: str, requested: int | None, *, settings, default: int) -> int:
    """Validate API ceiling first (invalid query=2), configured budget second (4)."""
    limit = min(default, settings.limits.max_results, 100) if requested is None else requested
    if (not isinstance(text, str) or not text.strip()
            or len(text) > 512 or not 1 <= limit <= 100):
        raise SnapshotError("QUERY_INVALID", "Query is outside the service contract.")
    if len(text) > settings.limits.query_chars or limit > settings.limits.max_results:
        raise SnapshotError("LIMIT_EXCEEDED", "Configured search budget exceeded.")
    return limit


def _run_command(args: argparse.Namespace) -> tuple[int, dict]:
    command = args.command
    if command == "init":
        payload = initialise_config(
            config=args.config, game_root=args.game_root, data_dir=args.data_dir,
            language=args.language,
        )
        return 0, payload
    settings = _load_checked(args)
    selected_limit = None
    if command in {"search", "show", "refs"}:
        selected = args.text if command == "search" else args.game_id
        selected_limit = _bounded_query_limit(
            selected, args.limit, settings=settings,
            default=20 if command in {"search", "refs"} else 100,
        )
    repo = SnapshotRepository(settings.data_dir, game_root=settings.game_root)
    if command == "index":
        answer = index_technologies(repo, settings, allow_partial=args.allow_partial,
                                    **({"include_events": True} if args.include_events else {}),
                                    **({"full": True} if args.full else {}))
        return 0, {"schema_version": 1, "command": command, **answer}
    if command == "snapshots":
        rows, truncated = repo.list_snapshots(limit=args.limit, offset=args.offset)
        return 0, {
            "schema_version": 1, "command": command, "status": "ok",
            "results": list(rows), "truncated": truncated, "diagnostics": [],
            "limit": args.limit, "offset": args.offset,
        }
    if command == "diff":
        from stellaris_supporter.comparison import DiffQuery, DiffService
        limit = _bounded_query_limit(args.game_id or "diff", args.limit, settings=settings, default=20)
        result = DiffService(repo).compare(DiffQuery(
            args.before_snapshot, args.after_snapshot, args.kind, args.game_id,
            args.include_source_changes, limit, args.offset,
        ))
        payload = {"command": command, **result.to_dict()}
        return _response_code(payload), payload
    if command == "refs":
        from stellaris_supporter.references import ReferenceQuery, ReferenceService
        answer = ReferenceService(repo).refs(ReferenceQuery(
            args.game_id, args.kind, args.snapshot, args.entity_key, args.depth, selected_limit,
        ))
        payload = {"command": command, **answer.to_dict()}
        return _response_code(payload), payload
    service = SearchService(repo)
    try:
        if command == "search":
            result = service.search(Query(
                args.text, snapshot_id=args.snapshot, kind=args.kind,
                language=_language(settings.language), limit=selected_limit,
            ))
            payload = {"command": command, **asdict(result)}
            return _response_code(payload), payload
        if command == "show":
            response = AnswerService(service, repo).answer(
                Query(args.game_id, snapshot_id=args.snapshot, kind=args.kind,
                      language=_language(settings.language), limit=selected_limit),
                exact_game_id=True,
            )
            payload = {"command": command, **asdict(response)}
            return _response_code(payload), payload
        raise SnapshotError("QUERY_INVALID", "Unsupported CLI command.")
    finally:
        service.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError:
        rc, payload = _failed(None, "QUERY_INVALID", exit_code=2)
        if _wants_json(argv):
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print("error: Invalid command arguments.", file=sys.stderr)
        return rc
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "doctor":
        return _doctor_from_args(args)
    try:
        rc, payload = _run_command(args)
    except KeyboardInterrupt:
        rc, payload = _failed(args.command, "CANCELLED", exit_code=130)
    except SnapshotError as exc:
        rc, payload = _failed(args.command, exc.code)
    except sqlite3.DatabaseError:
        rc, payload = _failed(args.command, "SQLITE_ERROR")
    except (OSError, RuntimeError, ValueError, TypeError, UnicodeError):
        # The user-facing error must not contain private paths, raw game text,
        # SQL details, or unexpected tracebacks. Report no unverified facts.
        rc, payload = _failed(args.command, "COMMAND_FAILED")
    try:
        # Preflight the complete serialized response for both output formats.
        serialized = _bounded_json(payload)
    except (SnapshotError, UnicodeError, TypeError, ValueError):
        rc, payload = _failed(args.command, "LIMIT_EXCEEDED")
        serialized = _bounded_json(payload)
    if args.format == "json":
        print(serialized)
    else:
        _emit_text(payload)
    return rc
