"""Technology-only CLI indexing pipeline; every input is a verified live source.

This module deliberately composes existing inventory, parser, adapter, localisation,
snapshot and activation contracts. No inferred effective game rules or network I/O.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from stellaris_supporter.config import Settings
from stellaris_supporter.discovery.inventory import scan_inventory
from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import BlockNode, PairNode, parse_bytes
from stellaris_supporter.storage import (
    SnapshotError,
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    snapshot_identity,
)
from stellaris_supporter.storage.cache import _read_verified_file, live_source_relative_path

# Explicit v0.1 scope: no implicit mods, DLC, or general game directory crawl.
_INDEX_ROOTS = (
    ("common/technology", ".txt"),
    ("localisation/korean", ".yml"),
    ("localisation/english", ".yml"),
)
_POLICY_VERSION = "cli-technology-localisation-v1"


def _language(value: str) -> str:
    languages = {"ko": "korean", "korean": "korean", "en": "english", "english": "english"}
    try:
        return languages[value.lower()]
    except KeyError as exc:
        raise SnapshotError("QUERY_INVALID", "CLI supports korean and english only.") from exc


def _inventory_sources(settings: Settings) -> tuple[SourceFileInput, ...]:
    root = settings.game_root
    if root is None:
        raise SnapshotError("GAME_ROOT_MISSING", "Explicit game root required.")
    if not root.is_dir():
        raise SnapshotError("GAME_ROOT_MISSING", "Game root is not a readable directory.")
    collected: list[SourceFileInput] = []
    count_bytes = 0
    count_files = 0
    for prefix, suffix in _INDEX_ROOTS:
        folder = root.joinpath(*prefix.split("/"))
        if folder.is_symlink():
            raise SnapshotError("PATH_REJECTED", "Index input directory is a link.")
        if not folder.exists():
            if prefix == "common/technology":
                raise SnapshotError("GAME_ROOT_MISSING", "Supported technology directory is absent.")
            continue
        result = scan_inventory(folder, limits=settings.limits, allowed_root=root)
        if not result.ok or result.inventory is None:
            diagnostic = next(
                (x for x in result.diagnostics if x.severity == "error"), None
            )
            raise SnapshotError(
                "PATH_REJECTED" if diagnostic is None else diagnostic.code,
                "Supported source inventory failed its safety checks.",
            )
        for entry in result.inventory.files:
            if not entry.relative_path.lower().endswith(suffix):
                continue
            relative = prefix + "/" + entry.relative_path
            path = root.joinpath(*relative.split("/"))
            if live_source_relative_path(path, root) != relative:
                raise SnapshotError("SOURCE_CHANGED", "Live source path binding changed.")
            original = path.stat(follow_symlinks=False)
            data = _read_verified_file(
                path, expected_hash=entry.sha256, expected_size=entry.size
            )
            if live_source_relative_path(path, root) != relative:
                raise SnapshotError("SOURCE_CHANGED", "Source changed physical path.")
            after = path.stat(follow_symlinks=False)
            if (
                original.st_size != after.st_size
                or original.st_mtime_ns != after.st_mtime_ns
                or (original.st_ino and after.st_ino and
                    (original.st_ino != after.st_ino or original.st_dev != after.st_dev))
            ):
                raise SnapshotError("SOURCE_CHANGED", "Source changed during capture.")
            count_files += 1
            count_bytes += len(data)
            if count_files > settings.limits.max_files or count_bytes > settings.limits.total_bytes:
                raise SnapshotError("LIMIT_EXCEEDED", "Index aggregate size exceeded.")
            collected.append(SourceFileInput(
                "base", "base_install", relative, data,
                expected_sha256=entry.sha256, live_path=path,
            ))
    if not any(x.relative_path.startswith("common/technology/") for x in collected):
        raise SnapshotError("GAME_ROOT_MISSING", "No supported technology scripts found.")
    return tuple(sorted(collected, key=lambda x: (x.source_kind, x.source_id, x.relative_path)))


def _policy(settings: Settings) -> SnapshotPolicy:
    language = _language(settings.language)
    payload = json.dumps(
        {"index_policy": _POLICY_VERSION, "language": language,
         "source_roots": [x[0] for x in _INDEX_ROOTS],
         "limits": settings.limits.to_dict()},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return SnapshotPolicy(
        "ordered-parser-1", "technology-adapter-1",
        hashlib.sha256(payload).hexdigest(),
        context_kind="base_install", game_version=None,
        game_version_source="unknown", branch="unknown",
        mod_state="unknown",
        analysis_context={"scope": "technology_and_localisation", "language": language},
    )


def _verify_adapted_ids(source: SourceFileInput, adapted) -> None:
    """Pre-stage R6 guard: compare candidate root against parsed original AST."""
    parsed = parse_bytes(source.data)
    direct = {
        (node.span.byte_start, node.span.byte_end): node
        for node in parsed.document.items
        if isinstance(node, PairNode) and isinstance(node.value, BlockNode)
    }
    for candidate in adapted.candidates:
        ref = candidate.source_ref
        node = direct.get((ref.byte_start, ref.byte_end))
        if (
            node is None or node.key_text != candidate.game_id
            or candidate.kind != "technology"
            or ref.file_sha256 != hashlib.sha256(source.data).hexdigest()
            or ref.relative_path != source.relative_path
            or ref.source_kind != source.source_kind
            or ref.source_id != source.source_id
        ):
            raise SnapshotError("SOURCE_CHANGED", "Adapter technology ID differs from source.")


def index_technologies(
    repository: SnapshotRepository, settings: Settings, *, allow_partial: bool = False,
) -> dict[str, object]:
    """Capture original source identities and atomically activate only verified data."""
    sources = _inventory_sources(settings)
    policy = _policy(settings)
    identity = snapshot_identity(sources, policy)
    sid = identity.snapshot_id
    previous = repository.active_snapshot_id()
    existing = repository.snapshot(sid)
    if existing is not None:
        if existing.status not in {"ready", "partial"}:
            raise SnapshotError("SNAPSHOT_EXISTS", "Unfinished or failed snapshot cannot be reused.")
        # Explicit source tuple rechecks exact root-relative physical path and SHA.
        repository.activate(sid, sources=sources, allow_partial=allow_partial)
        return {
            "snapshot_id": sid, "status": "partial" if existing.status == "partial" else "ok",
            "snapshot_status": existing.status,
            "activated": True, "reused": True, "previous_active": previous,
            "source_count": len(sources), "context_kind": "base_install",
            "game_version": None, "branch": "unknown", "diagnostics": [],
        }

    technology_results = []
    documents = []
    for source in sources:
        context = SourceContext(
            sid, source.source_kind, source.source_id, source.relative_path,
            hashlib.sha256(source.data).hexdigest(),
        )
        if source.relative_path.startswith("common/technology/"):
            adapted = adapt_technologies(
                parse_bytes(source.data), source.data, context,
            )
            _verify_adapted_ids(source, adapted)
            technology_results.append(adapted)
        else:
            documents.append(parse_localisation(source.data, context))
    catalog = build_localisation_catalog(tuple(documents))
    if not catalog.complete or any(d.severity == "error" for d in catalog.diagnostics):
        # stage_from_results accounts for individual reader errors; catalog-wide
        # errors also must never silently become a fully-ready snapshot.
        raise SnapshotError("SOURCE_CHANGED", "Localisation catalog is incomplete.")
    names = tuple(
        resolve_technology_name(candidate, catalog, requested_language=_language(settings.language))
        for result in technology_results for candidate in result.candidates
    )
    summary = repository.stage_from_results(
        sources, policy, technology_results=tuple(technology_results),
        localisation_documents=tuple(documents), localised_names=names,
    )
    stored = repository.snapshot(sid)
    if stored is None:
        raise SnapshotError("SQLITE_ERROR", "Staged snapshot was not stored.")
    # Requires caller consent for partial, never bypassing manifest/cache protection.
    repository.activate(sid, sources=sources, allow_partial=allow_partial)
    return {
        "snapshot_id": summary.snapshot_id,
        "status": "partial" if stored.status == "partial" else "ok",
        "snapshot_status": stored.status,
        "activated": True, "reused": False, "previous_active": previous,
        "source_count": len(sources), "context_kind": "base_install",
        "game_version": None, "branch": "unknown",
        "diagnostics": [],
    }
