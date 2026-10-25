"""Technology/localisation and opt-in event CLI indexing pipeline; every input is a verified live source.

This module deliberately composes existing inventory, parser, adapter, localisation,
snapshot and activation contracts. No inferred effective game rules or network I/O.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.config import Settings
from stellaris_supporter.discovery.inventory import scan_inventory
from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.domain.event_references import EXTRACTOR_VERSION, extract_event_records
from stellaris_supporter.domain.generic import adapt_domain
from stellaris_supporter.incremental import FileProducts, classify_files
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
from stellaris_supporter.weapon_data import TABLES

# Explicit v0.1 scope: no implicit mods, DLC, or general game directory crawl.
_INDEX_ROOTS = (
    ("common/technology", ".txt"),
    ("common/scripted_variables", ".txt"),
    ("common/component_templates", ".txt"),
    ("common/component_sets", ".txt"),
    ("localisation/korean", ".yml"),
    ("localisation/english", ".yml"),
)
_POLICY_VERSION = "cli-technology-localisation-v1"
_RESOURCE_LIMIT_CODES = frozenset({
    "LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT",
    "PARSE_DIAGNOSTIC_LIMIT",
})


def _check_cancel(cancel):
    if cancel is not None and cancel():
        raise SnapshotError("CANCELLED", "Indexing cancelled before activation.")


def _reject_resource_limits(diagnostics) -> None:
    """Resource exhaustion is never user-consent partial, even with no candidates."""
    if any(item.code in _RESOURCE_LIMIT_CODES for item in diagnostics):
        raise SnapshotError("LIMIT_EXCEEDED", "Source parser/resolver resource limit reached.")



def _language(value: str) -> str:
    languages = {"ko": "korean", "korean": "korean", "en": "english", "english": "english"}
    try:
        return languages[value.lower()]
    except KeyError as exc:
        raise SnapshotError("QUERY_INVALID", "CLI supports korean and english only.") from exc


def _inventory_sources(settings: Settings, *, include_events: bool = False, cancel: Callable[[], bool] | None = None, pool=None) -> tuple[SourceFileInput, ...]:
    root = settings.game_root
    if root is None:
        raise SnapshotError("GAME_ROOT_MISSING", "Explicit game root required.")
    if not root.is_dir():
        raise SnapshotError("GAME_ROOT_MISSING", "Game root is not a readable directory.")
    collected: list[SourceFileInput] = []
    count_bytes = 0
    count_files = 0
    roots = (*_INDEX_ROOTS, ("events", ".txt")) if include_events else _INDEX_ROOTS
    for prefix, suffix in roots:
        _check_cancel(cancel)
        folder = root.joinpath(*prefix.split("/"))
        _check_components(folder)
        if folder.is_symlink():
            raise SnapshotError("PATH_REJECTED", "Index input directory is a link.")
        if not folder.exists():
            if prefix == "common/technology":
                raise SnapshotError("GAME_ROOT_MISSING", "Supported technology directory is absent.")
            continue
        result = scan_inventory(
            folder, limits=settings.limits, allowed_root=root,
            include_suffixes=(".txt", ".csv") if prefix == "common/component_templates" else (suffix,),
            **({"include_file": lambda relative: relative.lower().endswith(".txt") or "common/component_templates/"+relative in TABLES} if prefix == "common/component_templates" else {}),
        )
        if not result.ok or result.inventory is None:
            diagnostic = next(
                (x for x in result.diagnostics if x.severity == "error"), None
            )
            raise SnapshotError(
                "PATH_REJECTED" if diagnostic is None else diagnostic.code,
                "Supported source inventory failed its safety checks.",
            )
        for entry in result.inventory.files:
            if prefix == "common/component_templates" and entry.relative_path.endswith(".csv"):
                if "common/component_templates/" + entry.relative_path not in TABLES:
                    continue
            _check_cancel(cancel)
            if not entry.relative_path.lower().endswith(suffix) and not (prefix == "common/component_templates" and "common/component_templates/"+entry.relative_path in TABLES):
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
            captured = SourceFileInput(
                "base", "base_install", relative, data,
                expected_sha256=entry.sha256, live_path=path,
            )
            if pool is not None:
                from stellaris_supporter.storage.source_pool import CachedSource
                descriptor = captured.descriptor()
                pool.cache.put(data, descriptor.file_sha256)
                captured = CachedSource(descriptor, path, pool)
            collected.append(captured)
    if not any(x.relative_path.startswith("common/technology/") for x in collected):
        raise SnapshotError("GAME_ROOT_MISSING", "No supported technology scripts found.")
    return tuple(sorted(collected, key=lambda x: (x.source_kind, x.source_id, x.relative_path)))


def _policy(settings: Settings, *, include_events: bool = False) -> SnapshotPolicy:
    language = _language(settings.language)
    roots = (*_INDEX_ROOTS, ("events", ".txt")) if include_events else _INDEX_ROOTS
    payload = json.dumps(
        {"index_policy": _POLICY_VERSION if not include_events else EXTRACTOR_VERSION, "language": language,
         "source_roots": [x[0] for x in roots],
         "limits": settings.limits.to_dict()},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return SnapshotPolicy(
        "ordered-parser-1", "technology-adapter-1",
        hashlib.sha256(payload).hexdigest(),
        context_kind="base_install", game_version=None,
        game_version_source="unknown", branch="unknown",
        mod_state="unknown",
        analysis_context={"scope": "technology_events_localisation" if include_events else "technology_and_localisation", "language": language,
                          **({"event_references": EXTRACTOR_VERSION} if include_events else {})},
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


def _index_legacy(
    repository: SnapshotRepository, settings: Settings, *, allow_partial: bool = False,
    include_events: bool = False, full: bool = False,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Capture, reuse compatible neutral products, then compare-and-swap activation."""
    def capture():
        _check_cancel(cancel)
        if cancel is not None:
            return _inventory_sources(settings, include_events=include_events, cancel=cancel)
        return (_inventory_sources(settings, include_events=True)
                if include_events else _inventory_sources(settings))

    previous = repository.active_snapshot_id()
    sources = capture()
    policy = _policy(settings, include_events=True) if include_events else _policy(settings)
    identity = snapshot_identity(sources, policy)
    sid = identity.snapshot_id
    baseline = () if previous is None else repository.source_manifest(previous)
    changes = classify_files(baseline, sources)
    processing = {"mode": "full" if full else "incremental", "parsed_files": 0,
                  "reused_files": 0, "file_changes": {k: len(v) for k, v in changes.items()},
                  "reprocess_reason": "requested_full" if full else None}

    def recheck_sources():
        try:
            current = capture()
        except SnapshotError as exc:
            if exc.code == "GAME_ROOT_MISSING":
                raise SnapshotError("SOURCE_CHANGED", "Source inventory changed during indexing.") from exc
            raise
        if snapshot_identity(current, policy).sources != identity.sources:
            raise SnapshotError("SOURCE_CHANGED", "Source membership or hash changed during indexing.")

    def activate():
        _check_cancel(cancel)
        repository.activate(sid, sources=sources, allow_partial=allow_partial,
                            expected_active=previous, source_check=recheck_sources,
                            **({"cancel": cancel} if cancel is not None else {}))

    def response(stored, reused):
        return {"snapshot_id": sid, "status": "partial" if stored.status == "partial" else "ok",
                "snapshot_status": stored.status, "activated": True, "reused": reused,
                "previous_active": previous, "source_count": len(sources),
                "context_kind": "base_install", "game_version": None, "branch": "unknown",
                "diagnostics": [], "processing": processing}

    existing = repository.snapshot(sid)
    if existing is not None:
        if existing.status not in {"ready", "partial"}:
            raise SnapshotError("SNAPSHOT_EXISTS", "Unfinished or failed snapshot cannot be reused.")
        if existing.status == "ready" and not full:
            activate()
            processing["mode"] = "snapshot_reuse"
            processing["reused_files"] = len(sources)
            return response(existing, True)

    products = FileProducts(repository, policy)
    technology_results, event_results, event_records, documents = [], [], [], []
    for source in sources:
        _check_cancel(cancel)
        context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                                hashlib.sha256(source.data).hexdigest())
        product = None if full else products.get(source, context)
        cached = product is not None
        if source.relative_path.startswith("common/technology/"):
            if product is None:
                product = adapt_technologies(parse_bytes(source.data), source.data, context)
                _verify_adapted_ids(source, product)
            _reject_resource_limits(product.diagnostics)
            technology_results.append(product)
        elif source.relative_path.startswith("events/"):
            if product is None:
                parsed = parse_bytes(source.data)
                adapted = adapt_domain(parsed, source.data, context, "event")
                _reject_resource_limits(adapted.diagnostics)
                if adapted.blocked:
                    raise SnapshotError("LIMIT_EXCEEDED", "Event adapter budget exhausted.")
                product = (adapted, extract_event_records(adapted.candidates, parsed, source.data, context))
            adapted, records = product
            _reject_resource_limits(adapted.diagnostics)
            if adapted.blocked:
                raise SnapshotError("LIMIT_EXCEEDED", "Event adapter budget exhausted.")
            event_results.append(adapted)
            event_records.extend(records)
        else:
            if product is None:
                product = parse_localisation(source.data, context)
            documents.append(product)
        processing["reused_files" if cached else "parsed_files"] += 1
        if not cached:
            products.put(source, product)
    products.flush()
    if not full and not processing["reused_files"]:
        processing["mode"] = "full_fallback"
        processing["reprocess_reason"] = "no_compatible_file_products"
    catalog = build_localisation_catalog(tuple(documents))
    for diagnostic in catalog.diagnostics:
        if diagnostic.code in {"LIMIT_EXCEEDED", "LOC_SNAPSHOT_MISMATCH"}:
            raise SnapshotError("LIMIT_EXCEEDED" if diagnostic.code == "LIMIT_EXCEEDED" else "SOURCE_CHANGED",
                                "Localisation catalog identity or bound is invalid.")
    names = tuple(resolve_technology_name(candidate, catalog,
                  requested_language=_language(settings.language))
                  for result in technology_results for candidate in result.candidates)
    for name in names:
        _reject_resource_limits(name.localisation.diagnostics)
        if name.localisation.truncated:
            raise SnapshotError("LIMIT_EXCEEDED", "Localisation expansion was truncated.")
    recheck_sources()
    if existing is None:
        repository.stage_from_results(
            sources, policy, technology_results=tuple(technology_results),
            localisation_documents=tuple(documents), localised_names=names,
            **({"cancel": cancel} if cancel is not None else {}),
            **({"event_results": tuple(event_results), "event_records": tuple(event_records)}
               if include_events else {}),
        )
    else:
        repository.verify_index_products(sid, tuple(c for r in technology_results for c in r.candidates)
                                         + tuple(event_records), documents, names)
    stored = repository.snapshot(sid)
    if stored is None:
        raise SnapshotError("SQLITE_ERROR", "Staged snapshot was not stored.")
    activate()
    return response(stored, existing is not None)


def index_technologies(repository, settings, *, allow_partial=False, include_events=False,
                       full=False, cancel=None, progress=None):
    from stellaris_supporter.disk_index import index_disk
    return index_disk(repository, settings, allow_partial=allow_partial, include_events=include_events,
                      full=full, cancel=cancel, progress=progress)
