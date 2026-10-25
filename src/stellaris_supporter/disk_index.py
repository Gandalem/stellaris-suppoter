"""Option 2: durable file products, narrow snapshot projection and atomic publication."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from stellaris_supporter.domain import SourceContext
from stellaris_supporter.domain.event_references import extract_event_records
from stellaris_supporter.domain.generic import adapt_domain
from stellaris_supporter.incremental import FileProducts, classify_files
from stellaris_supporter.localisation.resolver import TechnologyLocalisedName
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.static_values import VERSION as VALUE_VERSION
from stellaris_supporter.static_values import StaticCatalog, StaticProducts
from stellaris_supporter.storage import SnapshotError, snapshot_identity
from stellaris_supporter.storage.catalogue import VERSION, FileCatalogue, index_lock, packed
from stellaris_supporter.storage.source_pool import SourcePool
from stellaris_supporter.weapon_data import VERSION as WEAPON_VERSION
from stellaris_supporter.weapon_data import WeaponContext, WeaponProducts
from stellaris_supporter.weapon_data import supported as weapon_source


def is_disk_snapshot(repo, sid):
    with repo._connection(read_only=True) as conn:
        row = conn.execute(
            "SELECT policy_json FROM snapshots WHERE snapshot_id=?", (sid,)
        ).fetchone()
    return bool(row and VERSION in row[0])


def _discard_unpublished(repo, sid):
    with repo._connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT status FROM snapshots WHERE snapshot_id=?", (sid,)
            ).fetchone()
            active = conn.execute(
                "SELECT value FROM settings WHERE key='active_snapshot'"
            ).fetchone()
            if row and row[0] in {"building", "failed"}:
                if active and active[0] == sid:
                    raise SnapshotError("SOURCE_CHANGED", "Active snapshot cannot be discarded.")
                for table in (
                    "relations",
                    "search_documents",
                    "diagnostics",
                    "localisation_entries",
                    "entities",
                    "source_files",
                    "snapshots",
                ):
                    conn.execute("DELETE FROM " + table + " WHERE snapshot_id=?", (sid,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def index_disk(
    repo,
    settings,
    *,
    allow_partial=False,
    include_events=False,
    full=False,
    cancel=None,
    progress=None,
):
    from stellaris_supporter import cli_index as cli

    def check():
        cli._check_cancel(cancel)

    def report(phase, done=0, total=0):
        if progress:
            progress({"phase": phase, "done": done, "total": total})

    with index_lock(settings.data_dir):
        store = FileCatalogue(repo)
        job = store.start()
        pool = SourcePool(repo.cache)
        try:
            previous = repo.active_snapshot_id()

            def capture():
                check()
                return cli._inventory_sources(
                    settings, include_events=include_events, cancel=cancel, pool=pool
                )

            report("inventory")
            sources = capture()
            neutral_settings = replace(settings, language="korean")
            parser_policy = cli._policy(neutral_settings, include_events=include_events)
            policy = parser_policy
            policy = replace(
                policy,
                analysis_context={**dict(policy.analysis_context), "localisation_storage": VERSION, "card_values": VALUE_VERSION, "weapons": WEAPON_VERSION},
            )
            identity = snapshot_identity(sources, policy)
            sid = identity.snapshot_id
            processing = {
                "mode": "full" if full else "incremental",
                "parsed_files": 0,
                "reused_files": 0,
                "file_changes": {
                    k: len(v)
                    for k, v in classify_files(
                        () if previous is None else repo.source_manifest(previous), sources
                    ).items()
                },
                "reprocess_reason": "requested_full" if full else None,
                "derived_reused": 0,
                "derived_rebuilt": 0,
            }

            def recheck():
                try:
                    current = capture()
                except SnapshotError as exc:
                    if exc.code == "GAME_ROOT_MISSING":
                        raise SnapshotError(
                            "SOURCE_CHANGED", "Supported files disappeared during indexing."
                        ) from exc
                    raise
                if snapshot_identity(current, policy).sources != identity.sources:
                    raise SnapshotError(
                        "SOURCE_CHANGED", "Source membership or bytes changed during indexing."
                    )

            def activate():
                report("publish")
                repo.activate(
                    sid,
                    sources=sources,
                    allow_partial=allow_partial,
                    cancel=cancel,
                    expected_active=previous,
                    source_check=recheck,
                )

            def result(reused=False):
                stored = repo.snapshot(sid)
                return {
                    "snapshot_id": sid,
                    "status": "partial" if stored.status == "partial" else "ok",
                    "snapshot_status": stored.status,
                    "activated": True,
                    "reused": reused,
                    "previous_active": previous,
                    "source_count": len(sources),
                    "context_kind": "base_install",
                    "game_version": None,
                    "branch": "unknown",
                    "diagnostics": [],
                    "processing": processing,
                    "storage": {
                        "localisation_entries": store.conn.execute(
                            "SELECT coalesce(sum(f.entry_count),0) FROM snapshot_files m JOIN file_versions f USING(file_id) WHERE m.sid=?",
                            (sid,),
                        ).fetchone()[0],
                        "partial_localisation_files": store.conn.execute(
                            "SELECT count(*) FROM snapshot_files m JOIN file_versions f USING(file_id) WHERE m.sid=? AND f.complete=0",
                            (sid,),
                        ).fetchone()[0],
                    },
                }

            existing = repo.snapshot(sid)
            reusable = bool(existing and existing.status in {"ready", "partial"} and not full)
            if reusable:
                try:
                    current_receipt = store.bind(sid, sources)
                    with repo._connection(read_only=True) as conn:
                        expected = conn.execute(
                            "SELECT value FROM settings WHERE key=?", ("localisation-v2:" + sid,)
                        ).fetchone()
                    reusable = bool(expected and expected[0] == current_receipt)
                    if reusable:
                        WeaponContext(repo, sid, cancel=check)
                        variables = StaticCatalog(repo, sid)
                        for key in variables.files:
                            meta = variables.files[key]
                            repo.cache.read(meta["product_sha"], meta["product_size"])
                except SnapshotError as exc:
                    if exc.code not in {"SOURCE_CHANGED", "CACHE_MISSING"}:
                        raise
                    reusable = False
            if reusable:
                processing.update(mode="snapshot_reuse", reused_files=len(sources))
                from stellaris_supporter.retrieval import Query, SearchService

                service = SearchService(repo)
                try:
                    prepared = service.search(Query("__projection_preparation__", snapshot_id=sid))
                    if prepared.status == "error":
                        raise SnapshotError(
                            prepared.diagnostics[0].code,
                            "Persistent search projection is unavailable.",
                        )
                finally:
                    service.close()
                activate()
                store.finish(job, "done", sid)
                return result(True)
            _discard_unpublished(repo, sid)
            products = FileProducts(repo, parser_policy)
            values = StaticProducts(repo)
            weapons = WeaponProducts(repo)
            technologies, events, records = [], [], []
            for number, source in enumerate(sources, 1):
                check()
                descriptor = source.descriptor()
                context = SourceContext(sid, *descriptor.key, descriptor.file_sha256)
                if source.relative_path.startswith("localisation/"):
                    _, reused = store.ingest(source, cancel, force=full)
                elif weapon_source(source.relative_path):
                    reused, parsed_weapon = weapons.ingest(source, force=full)
                    if source.relative_path.lower().endswith(".txt"):
                        values.ingest(source, parsed=parsed_weapon, force=full)
                elif source.relative_path.startswith("common/scripted_variables/"):
                    reused = values.ingest(source, force=full)
                else:
                    parsed = None
                    product = None if full else products.get(source, context)
                    reused = product is not None
                    if source.relative_path.startswith("common/technology/"):
                        if product is None:
                            parsed = cli.parse_bytes(source.data)
                            product = cli.adapt_technologies(parsed, source.data, context)
                        if not reused:
                            cli._verify_adapted_ids(source, product)
                        else:
                            from stellaris_supporter.parsing import lex_bytes

                            for candidate in product.candidates:
                                ref = candidate.source_ref
                                raw = source.data[
                                    ref.byte_start : min(ref.byte_end, ref.byte_start + 4096)
                                ]
                                tokens = [
                                    t
                                    for t in lex_bytes(raw).tokens
                                    if t.kind not in {"whitespace", "comment", "bom"}
                                ]
                                if (
                                    len(tokens) < 2
                                    or tokens[0].text != candidate.game_id
                                    or tokens[1].text != "="
                                ):
                                    raise SnapshotError(
                                        "SOURCE_CHANGED",
                                        "Cached technology ID differs from original root.",
                                    )
                        cli._reject_resource_limits(product.diagnostics)
                        technologies.append(product)
                        values.ingest(source, parsed=parsed, force=full)
                    else:
                        if product is None:
                            parsed = parse_bytes(source.data)
                            adapted = adapt_domain(parsed, source.data, context, "event")
                            product = (
                                adapted,
                                extract_event_records(
                                    adapted.candidates, parsed, source.data, context
                                ),
                            )
                        adapted, extracted = product
                        cli._reject_resource_limits(adapted.diagnostics)
                        if adapted.blocked:
                            raise SnapshotError(
                                "LIMIT_EXCEEDED", "Event parser reached its budget."
                            )
                        events.append(adapted)
                        records.extend(extracted)
                    if not reused:
                        products.put(source, product)
                processing["reused_files" if reused else "parsed_files"] += 1
                store.conn.execute(
                    "UPDATE jobs SET files_done=?,files_total=? WHERE job_id=?",
                    (number, len(sources), job),
                )
                report("parse", number, len(sources))
            products.flush()
            if not full and not processing["reused_files"]:
                processing.update(
                    mode="full_fallback", reprocess_reason="no_compatible_file_products"
                )
            receipt = store.bind(sid, sources)
            catalog = store.catalogue(sid)
            primary = []
            alternate = {}
            for result_group in technologies:
                for candidate in result_group.candidates:
                    check()
                    for language in ("korean", "english"):
                        resolution, reused = catalog.resolve(candidate.game_id, language)
                        if resolution.truncated:
                            raise SnapshotError(
                                "LIMIT_EXCEEDED",
                                "Localisation reference expansion exceeded its budget.",
                            )
                        processing["derived_reused" if reused else "derived_rebuilt"] += 1
                        alternate[(candidate.source_ref, language)] = resolution
                        if language == "korean":
                            primary.append(TechnologyLocalisedName(candidate, resolution))
                        catalog.resolve(candidate.game_id + "_desc", language)
            documents = catalog.documents()
            report("store")
            if existing is None or existing.status in {"failed", "building"}:
                repo.stage_from_results(
                    sources,
                    policy,
                    technology_results=tuple(technologies),
                    event_results=tuple(events),
                    event_records=tuple(records),
                    localisation_documents=documents,
                    localised_names=tuple(primary),
                    extra_partial=values.incomplete or weapons.incomplete,
                    cancel=cancel,
                )
            else:
                repo.verify_index_products(
                    sid,
                    tuple(c for g in technologies for c in g.candidates) + tuple(records),
                    documents,
                    tuple(primary),
                    additional_kinds=("component_template",),
                )
            with repo._connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO settings VALUES(?,?)",
                        ("localisation-v2:" + sid, receipt),
                    )
                    values.publish(conn, sid)
                    weapons.publish(conn, sid)
                    for row in conn.execute(
                        "SELECT entity_key,source_kind,source_id,relative_path,byte_start,byte_end FROM entities WHERE snapshot_id=? AND kind='technology'",
                        (sid,),
                    ).fetchall():
                        candidate = next(
                            (
                                c
                                for g in technologies
                                for c in g.candidates
                                if (
                                    c.source_ref.source_kind,
                                    c.source_ref.source_id,
                                    c.source_ref.relative_path,
                                    c.source_ref.byte_start,
                                    c.source_ref.byte_end,
                                )
                                == tuple(row)[1:]
                            ),
                            None,
                        )
                        if candidate:
                            for language in ("korean", "english"):
                                conn.execute(
                                    "INSERT OR REPLACE INTO search_documents VALUES(?,?,?,?)",
                                    (
                                        sid,
                                        row["entity_key"],
                                        "name:" + language,
                                        packed(
                                            alternate[(candidate.source_ref, language)].to_dict()
                                        ),
                                    ),
                                )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            WeaponContext(repo, sid, cancel=check)
            report("search")
            from stellaris_supporter.retrieval import Query, SearchService

            service = SearchService(repo)
            try:
                response = service.search(Query("__projection_preparation__", snapshot_id=sid))
                if response.status == "error":
                    raise SnapshotError(
                        response.diagnostics[0].code, "Search projection preparation failed."
                    )
            finally:
                service.close()
            activate()
            store.finish(job, "done", sid)
            report("done", len(sources), len(sources))
            return result(existing is not None)
        except Exception as exc:
            store.finish(
                job,
                "cancelled"
                if isinstance(exc, SnapshotError) and exc.code == "CANCELLED"
                else "failed",
                error=exc.code if isinstance(exc, SnapshotError) else type(exc).__name__,
            )
            if isinstance(exc, sqlite3.DatabaseError):
                raise SnapshotError("SQLITE_WRITE_ERROR", "File catalogue write failed.") from exc
            raise
        finally:
            store.close()
