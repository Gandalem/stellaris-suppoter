"""E-018/E-019: synthetic-only SQLite snapshot integration and fault injection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from dataclasses import replace
from pathlib import Path

import pytest

from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.storage import (
    SnapshotError,
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    canonical_json,
    normalise_relative_path,
    snapshot_identity,
)

POLICY_HASH = "a" * 64
TECH_SOURCE = b'demo_tech = { cost = @price prerequisites = { "demo_other" } }\n'
TECH_DUPLICATE = b'demo_tech = { cost = 0 }\n'
LOC_SOURCE = b'\xef\xbb\xbfl_korean:\r\n demo_tech:0 "\xed\x95\x9c\xea\xb8\x80"\r\n'
LOC_DUPLICATE = LOC_SOURCE + b' demo_tech:1 "again"\r\n'
LOC_ENGLISH = b'l_english:\n demo_tech:0 "Technology"\n'


def _policy(**overrides):
    return replace(
        SnapshotPolicy("parser-1", "adapter-1", POLICY_HASH), **overrides
    )


def _sources(tech: bytes = TECH_SOURCE, loc: bytes = LOC_SOURCE):
    return (
        SourceFileInput("synthetic", "demo", "common/technology/demo.txt", tech),
        SourceFileInput("synthetic", "demo", "localisation/korean/demo.yml", loc),
        SourceFileInput("synthetic", "demo", "localisation/english/demo.yml", LOC_ENGLISH),
    )


def _context(source: SourceFileInput, sid: str) -> SourceContext:
    return SourceContext(
        snapshot_id=sid, source_kind=source.source_kind, source_id=source.source_id,
        relative_path=normalise_relative_path(source.relative_path),
        file_sha256=hashlib.sha256(source.data).hexdigest(),
    )


def _records(sources, policy):
    sid = snapshot_identity(sources, policy).snapshot_id
    adapted = [
        adapt_technologies(parse_bytes(x.data), x.data, _context(x, sid))
        for x in sources if "technology" in x.relative_path
    ]
    documents = [
        parse_localisation(x.data, _context(x, sid))
        for x in sources if "localisation" in x.relative_path
    ]
    assert all(result.complete for result in adapted)
    assert all(doc.complete for doc in documents)
    candidates = tuple(c for result in adapted for c in result.candidates)
    catalog = build_localisation_catalog(tuple(documents))
    names = tuple(resolve_technology_name(c, catalog) for c in candidates)
    return candidates, tuple(e for doc in documents for e in doc.entries), names


def _stage(repo, sources=None, policy=None, **kwargs):
    sources = _sources() if sources is None else sources
    policy = _policy() if policy is None else policy
    candidates, entries, names = _records(sources, policy)
    return repo.stage(
        sources, policy, candidates=candidates, entries=entries,
        localised_names=names, **kwargs
    )


def _seed_active(repo):
    identity = _stage(repo)
    repo.activate(identity.snapshot_id)
    assert repo.active_snapshot_id() == identity.snapshot_id
    return identity.snapshot_id


def test_e018_canonical_json_is_explicit_and_order_independent() -> None:
    assert canonical_json({"b": [None, False, 0, []], "a": "한글"}) == (
        '{"a":"한글","b":[null,false,0,[]]}'.encode()
    )
    assert canonical_json({"z": 1, "a": 0}) == canonical_json({"a": 0, "z": 1})
    with pytest.raises(SnapshotError, match="Unsupported type"):
        canonical_json({"float": 1.25})


@pytest.mark.parametrize("path", [
    "../outside", "/absolute", "C:\\private\\a", "demo/../a",
    "demo//a", "demo/./a", "demo/CON", "demo/trailing.",
])
def test_e018_paths_reject_escape_and_cross_os_reserved_names(path: str) -> None:
    with pytest.raises(SnapshotError) as exc:
        normalise_relative_path(path)
    assert exc.value.code == "PATH_REJECTED"


def test_e018_slash_canonicalisation_preserves_case_and_rejects_non_nfc() -> None:
    assert normalise_relative_path("a\\b\\Demo.txt") == "a/b/Demo.txt"
    assert normalise_relative_path("a/demo.txt") != normalise_relative_path("a/Demo.txt")
    with pytest.raises(SnapshotError, match="NFC"):
        normalise_relative_path(unicodedata.normalize("NFD", "localisation/한글.yml"))


def test_e018_order_root_clock_invariance() -> None:
    sources = _sources()
    first = snapshot_identity(sources, _policy())
    assert first == snapshot_identity(tuple(reversed(sources)), _policy())
    assert first.snapshot_id == snapshot_identity(tuple(sources), _policy()).snapshot_id
    assert "tmp" not in first.policy_json
    # Clock and absolute temporary roots are absent from SourceFileInput IDs.
    assert "created_at" not in first.policy_json
    assert len(first.snapshot_id) == 64 and len(first.content_hash) == 64


@pytest.mark.parametrize("change", ["bytes", "path", "schema", "parser", "adapter", "policy", "context"])
def test_e018_meaningful_changes_alter_fingerprint(change: str) -> None:
    original = _sources()
    policy = _policy()
    before = snapshot_identity(original, policy)
    if change == "bytes":
        original = (replace(original[0], data=original[0].data + b"# changed\n"), *original[1:])
    elif change == "path":
        original = (replace(original[0], relative_path="common/technology/other.txt"), *original[1:])
    elif change == "schema":
        policy = replace(policy, schema_version=2)
    elif change == "parser":
        policy = replace(policy, parser_version="parser-2")
    elif change == "adapter":
        policy = replace(policy, adapter_version="adapter-2")
    elif change == "policy":
        policy = replace(policy, policy_hash="b" * 64)
    else:
        policy = replace(policy, analysis_context={"dlc": {"demo": True}})
    assert before.snapshot_id != snapshot_identity(original, policy).snapshot_id


def test_e018_renamed_windows_separator_produces_same_content_identity() -> None:
    original = _sources()
    new = replace(original[0], relative_path="common\\technology\\demo.txt")
    assert snapshot_identity(original, _policy()) == snapshot_identity(
        (new, *original[1:]), _policy()
    )


def test_e018_duplicate_source_identity_and_inventory_hash_mismatch_rejected() -> None:
    files = _sources()
    with pytest.raises(SnapshotError) as dup:
        snapshot_identity((files[0], files[0]), _policy())
    assert dup.value.code == "COLLISION_UNRESOLVED"
    bad = replace(files[0], expected_sha256="0"*64)
    with pytest.raises(SnapshotError) as mismatch:
        snapshot_identity((bad,), _policy())
    assert mismatch.value.code == "SOURCE_CHANGED"


def test_e018_sqlite_typed_round_trip_source_ref_localisation_and_relations(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    sid = _stage(repo, _sources(loc=LOC_DUPLICATE)).snapshot_id
    repo.activate(sid, allow_partial=True)
    entities = repo.entities()
    assert len(entities) == 1
    candidate = entities[0]["candidate"]
    assert candidate["game_id"] == "demo_tech"
    assert [x["name"] for x in candidate["fields"]] == ["cost", "prerequisites"]
    assert candidate["prerequisites"][0]["target_game_id"] == "demo_other"
    assert entities[0]["resolution"] == "raw_definition"
    assert entities[0]["localisation"]["resolution"] == "ambiguous"
    locs = repo.localisation_entries()
    assert [(x["key"], x["occurrence"]) for x in locs if x["language"] == "korean"] == [
        ("demo_tech", 1), ("demo_tech", 2)
    ]
    assert next(x for x in locs if x["language"] == "korean")["raw_value"] == "한글"
    ref = entities[0]["candidate"]["source_ref"]
    from stellaris_supporter.domain import SourceRef
    source_ref = SourceRef(**ref)
    assert repo.source_bytes(source_ref) == TECH_SOURCE[
        source_ref.byte_start:source_ref.byte_end
    ]
    assert len(repo.cache.read(hashlib.sha256(LOC_DUPLICATE).hexdigest(), len(LOC_DUPLICATE))) == len(LOC_DUPLICATE)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM relations").fetchone()[0] == 1
        assert set(row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )) >= {
            "snapshots","source_files","entities","localisation_entries",
            "relations","search_documents","diagnostics","settings",
        }
    assert repo.snapshot(sid).status == "partial"


def test_e018_duplicate_game_id_in_two_files_is_not_overwritten(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    sources = _sources() + (
        SourceFileInput("synthetic","demo","common/technology/dupe.txt",TECH_DUPLICATE),
    )
    sid = _stage(repo, sources).snapshot_id
    repo.activate(sid, allow_partial=True)
    found = repo.entities()
    assert [x["game_id"] for x in found] == ["demo_tech","demo_tech"]
    assert len({x["entity_key"] for x in found}) == 2
    assert [x["occurrence"] for x in found] == [1,2]


def test_e018_cross_snapshot_source_ref_and_payload_forgery_rejected(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    sources = _sources()
    candidates, entries, names = _records(sources, _policy())
    fake = replace(candidates[0], source_ref=replace(candidates[0].source_ref,snapshot_id="another"))
    with pytest.raises(SnapshotError) as exc:
        repo.stage(sources, _policy(), candidates=(fake,))
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() is None


def test_e018_cache_same_hash_reuse_preserves_separate_source_rows(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    sources=(
        SourceFileInput("synthetic","demo","a.txt",b"same bytes"),
        SourceFileInput("synthetic","demo","b.txt",b"same bytes"),
    )
    sid=repo.stage(sources,_policy()).snapshot_id
    repo.activate(sid)
    with sqlite3.connect(repo.db_path) as conn:
        rows=conn.execute(
            "SELECT relative_path, cache_sha256 FROM source_files ORDER BY relative_path"
        ).fetchall()
    assert [r[0] for r in rows] == ["a.txt", "b.txt"]
    assert rows[0][1]==rows[1][1]


def test_e019_first_activation_then_unchanged_active_during_second_stage(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    first=repo.stage((SourceFileInput("synthetic","demo","old.txt",b"one"),),_policy()).snapshot_id
    assert repo.active_snapshot_id() is None
    repo.activate(first)
    next_sources=(SourceFileInput("synthetic","demo","new.txt",b"two"),)
    second=repo.stage(next_sources,_policy()).snapshot_id
    assert repo.active_snapshot_id()==first
    assert repo.snapshot(second).status=="ready"
    repo.activate(second)
    assert repo.active_snapshot_id()==second
    assert repo.snapshot(first).status=="ready"


def test_e019_partial_requires_explicit_approval(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    first=_stage(repo,partial=True).snapshot_id
    assert repo.snapshot(first).status=="partial"
    with pytest.raises(SnapshotError) as error:
        repo.activate(first)
    assert error.value.code=="PARTIAL_INDEX"
    assert repo.active_snapshot_id() is None
    repo.activate(first,allow_partial=True)
    assert repo.active_snapshot_id()==first


@pytest.mark.parametrize("failure", ["raise","cancel"])
def test_e019_stage_failure_cannot_replace_previous_active(tmp_path: Path,failure: str) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    new=(SourceFileInput("synthetic","demo","new.txt",b"new"),)
    def broken():
        if failure=="raise":
            raise RuntimeError("injected failure")
    with pytest.raises((RuntimeError,SnapshotError)):
        repo.stage(
            new, _policy(), before_ready=broken,
            cancel=(lambda: failure=="cancel"),
        )
    assert repo.active_snapshot_id()==old
    assert len(repo.entities())==1


@pytest.mark.parametrize("mode", ["raise","cancel"])
def test_e019_activation_before_commit_rolls_back_pointer(tmp_path: Path,mode: str) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    new=repo.stage((SourceFileInput("synthetic","demo","next.txt",b"next"),),_policy()).snapshot_id
    called=[False]
    def hook():
        called[0]=True
        if mode=="raise":
            raise RuntimeError("injected before commit")
    def cancel():
        return mode=="cancel" and called[0]
    with pytest.raises((RuntimeError,SnapshotError)):
        repo.activate(new,before_commit=hook,cancel=cancel)
    assert repo.active_snapshot_id()==old
    assert repo.snapshot(new).status=="ready"
    assert len(repo.entities())==1


def test_e019_corrupted_or_missing_cache_blocks_activation(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    data=b"new data"
    new=repo.stage((SourceFileInput("synthetic","demo","new.txt",data),),_policy()).snapshot_id
    path=repo.cache._path(hashlib.sha256(data).hexdigest())
    path.write_bytes(b"wrong")
    with pytest.raises(SnapshotError):
        repo.activate(new)
    assert repo.active_snapshot_id()==old
    path.unlink()
    with pytest.raises(SnapshotError):
        repo.activate(new)
    assert repo.active_snapshot_id()==old


def test_e019_live_source_changed_between_staging_and_activation(tmp_path: Path) -> None:
    game=tmp_path/"game"
    game.mkdir()
    origin=game/"source.txt"
    origin.write_bytes(b"original")
    repo=SnapshotRepository(tmp_path/"data",game_root=game)
    old=repo.stage((SourceFileInput("synthetic","demo","old.txt",b"old"),),_policy()).snapshot_id
    repo.activate(old)
    live=SourceFileInput("synthetic","demo","source.txt",b"original",live_path=origin)
    sid=repo.stage((live,),_policy()).snapshot_id
    origin.write_bytes(b"changed")
    with pytest.raises(SnapshotError) as exc:
        repo.activate(sid,sources=(live,))
    assert exc.value.code=="SOURCE_CHANGED"
    assert repo.active_snapshot_id()==old
    assert origin.read_bytes()==b"changed"


def test_e019_live_origin_requires_fresh_manifest(tmp_path: Path) -> None:
    game=tmp_path/"game"
    game.mkdir()
    origin=game/"s.txt"
    origin.write_bytes(b"demo")
    repo=SnapshotRepository(tmp_path/"data",game_root=game)
    live=SourceFileInput("synthetic","demo","s.txt",b"demo",live_path=origin)
    sid=repo.stage((live,),_policy()).snapshot_id
    with pytest.raises(SnapshotError) as exc:
        repo.activate(sid)
    assert exc.value.code=="SOURCE_UNVERIFIED"
    repo.activate(sid,sources=(live,))
    assert repo.active_snapshot_id()==sid


def test_e019_database_lock_failure_is_finite_and_previous_active_survives(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    sid=repo.stage((SourceFileInput("synthetic","demo","new.txt",b"new"),),_policy()).snapshot_id
    with sqlite3.connect(repo.db_path, isolation_level=None) as locking:
        locking.execute("BEGIN IMMEDIATE")
        with pytest.raises(SnapshotError) as exc:
            repo.activate(sid)
        assert exc.value.code=="SQLITE_BUSY"
        locking.execute("ROLLBACK")
    assert repo.active_snapshot_id()==old
    repo.activate(sid)
    assert repo.active_snapshot_id()==sid


def test_e019_interrupted_build_detected_and_recovered_without_active_loss(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    newer=(SourceFileInput("synthetic","demo","interrupted.txt",b"x"),)
    sid=snapshot_identity(newer,_policy()).snapshot_id
    def interrupt():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        repo.stage(newer,_policy(),before_ready=interrupt)
    assert repo.snapshot(sid).status=="building"
    reopened=SnapshotRepository(tmp_path/"data")
    assert reopened.snapshot(sid).status=="building"
    assert reopened.active_snapshot_id()==old
    assert reopened.recover_interrupted()==(sid,)
    assert reopened.snapshot(sid).status=="failed"
    assert reopened.active_snapshot_id()==old


def test_e019_incompatible_new_schema_refuses_writes(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    old=_seed_active(repo)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA user_version=999")
    with pytest.raises(SnapshotError) as exc:
        SnapshotRepository(tmp_path/"data")
    assert exc.value.code=="SCHEMA_VERSION_UNSUPPORTED"
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key='active_snapshot'").fetchone()[0]==old


def test_e019_symlink_cache_and_private_data_overlap_rejected(tmp_path: Path) -> None:
    game=tmp_path/"game"
    game.mkdir()
    with pytest.raises(SnapshotError) as overlap:
        SnapshotRepository(game/"cache",game_root=game)
    assert overlap.value.code=="PATH_REJECTED"
    link=tmp_path/"linked"
    try:
        link.symlink_to(game, target_is_directory=True)
    except OSError:
        return  # Path-overlap negative check already ran; no test skip.
    with pytest.raises(SnapshotError) as unsafe:
        SnapshotRepository(link)
    assert unsafe.value.code=="PATH_REJECTED"


def test_e019_backup_uses_sqlite_consistent_backup_api(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    sid=_seed_active(repo)
    copied=repo.backup("synthetic-backup")
    with sqlite3.connect(copied) as backup:
        assert backup.execute(
            "SELECT value FROM settings WHERE key='active_snapshot'"
        ).fetchone()[0]==sid
        assert backup.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    with pytest.raises(SnapshotError):
        repo.backup("../escape")
    assert repo.active_snapshot_id()==sid


def test_e019_same_snapshot_never_silently_overwrites_and_is_readable(tmp_path: Path) -> None:
    repo=SnapshotRepository(tmp_path/"data")
    sid=_seed_active(repo)
    with pytest.raises(SnapshotError) as exc:
        _stage(repo)
    assert exc.value.code=="SNAPSHOT_EXISTS"
    assert repo.active_snapshot_id()==sid
    assert repo.entities(snapshot_id=sid)


def test_e018_false_zero_and_empty_collections_are_not_collapsed() -> None:
    payload={"number":0,"false":False,"missing":None,"empty":[]}
    assert json.loads(canonical_json(payload))==payload
    assert len(set(type(v) for v in payload.values()))==4



def test_e018_case_collision_is_rejected_without_merging_sources() -> None:
    files = (
        SourceFileInput("synthetic", "demo", "A/file.txt", b"x"),
        SourceFileInput("synthetic", "demo", "a/File.txt", b"y"),
    )
    with pytest.raises(SnapshotError) as exc:
        snapshot_identity(files, _policy())
    assert exc.value.code == "PATH_REJECTED"


def test_e018_different_schema_identity_is_not_implicitly_supported_by_db(tmp_path: Path) -> None:
    first = snapshot_identity(_sources(), _policy())
    revised = snapshot_identity(_sources(), _policy(schema_version=2))
    assert first.snapshot_id != revised.snapshot_id
    repo = SnapshotRepository(tmp_path / "data")
    with pytest.raises(SnapshotError) as exc:
        repo.stage(_sources(), _policy(schema_version=2))
    assert exc.value.code == "SCHEMA_VERSION_UNSUPPORTED"



def test_e019_active_remains_readable_while_staging_holds_writer_lock(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    old = _seed_active(repo)
    competing = SnapshotRepository(tmp_path / "data")
    def during_stage() -> None:
        assert competing.active_snapshot_id() == old
        assert len(competing.entities()) == 1
        with pytest.raises(SnapshotError) as blocked:
            competing.stage(
                (SourceFileInput("synthetic", "demo", "concurrent.txt", b"other"),), _policy()
            )
        assert blocked.value.code == "SQLITE_BUSY"
    staged = repo.stage(
        (SourceFileInput("synthetic", "demo", "new.txt", b"new"),),
        _policy(),
        before_ready=during_stage,
    ).snapshot_id
    assert repo.snapshot(staged).status == "ready"
    assert repo.active_snapshot_id() == old


def test_e019_injected_cache_write_failure_does_not_replace_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    old = _seed_active(repo)
    new = (SourceFileInput("synthetic", "demo", "cache_failed.txt", b"new"),)
    sid = snapshot_identity(new, _policy()).snapshot_id
    def disk_full(_data: bytes, _digest: str) -> None:
        raise OSError("synthetic disk-full injection")
    monkeypatch.setattr(repo.cache, "put", disk_full)
    with pytest.raises(SnapshotError) as exc:
        repo.stage(new, _policy())
    assert exc.value.code == "SQLITE_WRITE_ERROR"
    assert repo.active_snapshot_id() == old
    assert repo.snapshot(sid).status == "failed"
    assert len(repo.entities()) == 1


def test_e018_reader_diagnostic_is_not_lost_through_safe_storage_boundary(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    invalid = SourceFileInput("synthetic", "demo", "localisation/bad.yml", b"\xff\xfe")
    policy = _policy()
    sid = snapshot_identity((invalid,), policy).snapshot_id
    document = parse_localisation(invalid.data, _context(invalid, sid))
    assert not document.complete and document.diagnostics
    repo.stage_from_results(
        (invalid,), policy, localisation_documents=(document,),
    )
    assert repo.snapshot(sid).status == "partial"
    with sqlite3.connect(repo.db_path) as conn:
        row = conn.execute("SELECT code FROM diagnostics WHERE snapshot_id=?", (sid,)).fetchone()
        assert row is not None
        assert row[0] == document.diagnostics[0].code
    with pytest.raises(SnapshotError):
        repo.activate(sid)
    repo.activate(sid, allow_partial=True)
    assert repo.active_snapshot_id() == sid


def test_e018_stage_from_results_rejects_cross_document_source_bytes(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    input_source = SourceFileInput(
        "synthetic", "demo", "localisation/demo.yml", b'l_english:\n demo:0 "ok"\n'
    )
    policy = _policy()
    sid = snapshot_identity((input_source,), policy).snapshot_id
    doc = parse_localisation(input_source.data, _context(input_source, sid))
    forged = replace(doc, _source=b'wrong')
    with pytest.raises(SnapshotError) as exc:
        repo.stage_from_results(
            (input_source,), policy, localisation_documents=(forged,),
        )
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() is None


def test_e018_identity_stable_across_two_private_data_roots(tmp_path: Path) -> None:
    src = (SourceFileInput("synthetic", "demo", "a.txt", b"same"),)
    one = SnapshotRepository(tmp_path / "first")
    two = SnapshotRepository(tmp_path / "second")
    left = one.stage(src, _policy())
    right = two.stage(src, _policy())
    assert left == right
    one.activate(left.snapshot_id)
    two.activate(right.snapshot_id)
    assert one.active_snapshot_id() == two.active_snapshot_id()


def test_e018_canonical_json_budget_rejects_before_large_output_copy() -> None:
    with pytest.raises(SnapshotError) as exc:
        canonical_json({"raw": "x" * 10_000}, max_bytes=200)
    assert exc.value.code == "LIMIT_EXCEEDED"


def test_e019_future_schema_db_rejected_without_initialising_cache(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA user_version=2")
    # Prove the constructor does not create/cache anything on a future DB.
    old_cache = repo.data_dir / "cache"
    assert old_cache.is_dir()
    import shutil
    shutil.rmtree(old_cache)
    with pytest.raises(SnapshotError) as exc:
        SnapshotRepository(repo.data_dir)
    assert exc.value.code == "SCHEMA_VERSION_UNSUPPORTED"
    assert not old_cache.exists()



def test_e018_old_and_new_snapshots_keep_distinct_bytes_and_provenance(tmp_path: Path) -> None:
    from stellaris_supporter.domain import SourceRef

    repo = SnapshotRepository(tmp_path / "data")
    old = _stage(repo).snapshot_id
    repo.activate(old)
    first = repo.entities()[0]["candidate"]
    old_ref = SourceRef(**first["source_ref"])
    modified = _sources(tech=TECH_SOURCE.replace(b"@price", b"42"))
    new = _stage(repo, modified).snapshot_id
    repo.activate(new)
    assert old != new
    latest = repo.entities()
    previous = repo.entities(snapshot_id=old)
    assert latest[0]["snapshot_id"] == new
    assert previous[0]["snapshot_id"] == old
    assert latest[0]["entity_key"] != previous[0]["entity_key"]
    assert repo.source_bytes(old_ref) == old_ref.raw_bytes(TECH_SOURCE)
    wrong = replace(old_ref, snapshot_id=new)
    with pytest.raises(SnapshotError) as error:
        repo.source_bytes(wrong)
    assert error.value.code == "SOURCE_CHANGED"


def test_e019_live_file_changes_during_stage_cannot_replace_active(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    file = game / "origin.txt"
    file.write_bytes(b"first")
    repo = SnapshotRepository(tmp_path / "data", game_root=game)
    old = repo.stage(
        (SourceFileInput("synthetic", "demo", "old.txt", b"old"),), _policy()
    ).snapshot_id
    repo.activate(old)
    source = SourceFileInput(
        "synthetic", "demo", "origin.txt", b"first", live_path=file
    )
    identity = snapshot_identity((source,), _policy())
    def change_during_stage() -> None:
        file.write_bytes(b"second")
    with pytest.raises(SnapshotError) as exc:
        repo.stage((source,), _policy(), before_ready=change_during_stage)
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.snapshot(identity.snapshot_id).status == "failed"
    assert repo.active_snapshot_id() == old
    assert file.read_bytes() == b"second"
    assert not list(game.glob("*.sqlite3"))


def test_e019_commit_survives_reopen_and_failed_work_cannot_mask_it(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    repo = SnapshotRepository(directory)
    sid = _seed_active(repo)
    reopened = SnapshotRepository(directory)
    assert reopened.active_snapshot_id() == sid
    assert reopened.entities() == repo.entities()
    newer = (SourceFileInput("synthetic", "demo", "broken.txt", b"fail"),)
    with pytest.raises(RuntimeError, match="simulated stop"):
        reopened.stage(
            newer, _policy(),
            before_ready=lambda: (_ for _ in ()).throw(RuntimeError("simulated stop")),
        )
    assert SnapshotRepository(directory).active_snapshot_id() == sid



def test_e018_resource_limits_prevent_unbounded_manifest_or_file(tmp_path: Path) -> None:
    source = SourceFileInput("synthetic", "demo", "limited.txt", b"x")
    with pytest.raises(SnapshotError) as count:
        snapshot_identity((source,) * 50_001, _policy())
    assert count.value.code == "LIMIT_EXCEEDED"
    too_large = replace(source, data=b"x" * (16 * 1024 * 1024 + 1))
    with pytest.raises(SnapshotError) as size:
        snapshot_identity((too_large,), _policy())
    assert size.value.code == "LIMIT_EXCEEDED"
    assert not (tmp_path / "data").exists()


def test_e019_partial_approval_never_bypasses_source_hash_error(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    source = SourceFileInput(
        "synthetic", "demo", "forged.txt", b"data", expected_sha256="0" * 64
    )
    with pytest.raises(SnapshotError) as exc:
        repo.stage((source,), _policy(), partial=True)
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() is None


def test_e019_sqlite_write_connection_has_foreign_keys_wal_and_full(tmp_path: Path) -> None:
    from stellaris_supporter.storage.schema import connect

    repo = SnapshotRepository(tmp_path / "data")
    with connect(repo.db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 250



def test_e018_staging_manifest_scans_sources_linearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = SourceFileInput.descriptor
    calls = [0]
    def counted(self):
        calls[0] += 1
        return original(self)
    monkeypatch.setattr(SourceFileInput, "descriptor", counted)
    inputs = tuple(
        SourceFileInput("synthetic", "demo", f"bounded/{i:04d}.txt", b"x")
        for i in range(128)
    )
    repo = SnapshotRepository(tmp_path / "data")
    sid = repo.stage(inputs, _policy()).snapshot_id
    assert repo.snapshot(sid).status == "ready"
    # Identity + direct indexed source map + bounded rechecks, not O(N**2).
    assert calls[0] <= len(inputs) * 5



def test_e019_sqlite_entity_insert_failure_preserves_old_active(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    old = _seed_active(repo)
    revised = _sources(tech=TECH_SOURCE + b"# synthetic changed\n")
    new = snapshot_identity(revised, _policy()).snapshot_id
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(
            "CREATE TRIGGER synthetic_failure BEFORE INSERT ON entities "
            "BEGIN SELECT RAISE(ABORT, 'simulated insert failure'); END"
        )
    with pytest.raises(SnapshotError) as exc:
        _stage(repo, revised)
    assert exc.value.code == "SQLITE_ERROR"
    assert repo.snapshot(new).status == "failed"
    assert repo.active_snapshot_id() == old
    assert len(repo.entities()) == 1


def test_e019_staging_cancellation_after_building_never_activates(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "data")
    old = _seed_active(repo)
    new_sources = (SourceFileInput("synthetic", "demo", "cancel.txt", b"new"),)
    new = snapshot_identity(new_sources, _policy()).snapshot_id
    count = [0]
    def cancelled() -> bool:
        count[0] += 1
        return count[0] >= 3
    with pytest.raises(SnapshotError) as exc:
        repo.stage(new_sources, _policy(), cancel=cancelled)
    assert exc.value.code == "CANCELLED"
    assert repo.snapshot(new).status == "failed"
    assert repo.active_snapshot_id() == old



# PR #19 review follow-up: R1 live path binding, R2 Unicode fidelity,
# R3 identity policy limits, R4 cache pointer integrity, R5 documentation.

@pytest.mark.parametrize("kind", ["base", "mod"])
def test_r1_stage_target_cannot_be_swapped_for_same_hash_copy(
    tmp_path: Path, kind: str,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    origin, copy = game / "origin.txt", game / "copy.txt"
    origin.write_bytes(b"original")
    copy.write_bytes(b"original")
    repo = SnapshotRepository(tmp_path / "data", game_root=game)
    old = repo.stage(
        (SourceFileInput("synthetic", "demo", "old.txt", b"old"),), _policy()
    ).snapshot_id
    repo.activate(old)
    staged = SourceFileInput(
        kind, "unique-demo-source", "logical/technology/origin.txt",
        b"original", live_path=origin,
    )
    sid = repo.stage((staged,), _policy()).snapshot_id
    origin.write_bytes(b"changed")
    copied = replace(staged, live_path=copy)
    with pytest.raises(SnapshotError) as swapped:
        repo.activate(sid, sources=(copied,))
    assert swapped.value.code == "SOURCE_CHANGED"
    with pytest.raises(SnapshotError) as changed:
        repo.activate(sid, sources=(staged,))
    assert changed.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() == old


def test_r1_stage_binding_survives_reopen_and_never_leaks_absolute_root(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    target = game / "physical.txt"
    target.write_bytes(b"unchanged")
    directory = tmp_path / "data"
    repo = SnapshotRepository(directory, game_root=game)
    staged = SourceFileInput(
        "mod", "mod-source-1", "mod/script/virtual.txt", b"unchanged",
        live_path=target,
    )
    identity = repo.stage((staged,), _policy())
    with sqlite3.connect(repo.db_path) as conn:
        row = conn.execute(
            "SELECT live_required,live_relative_path,live_root_sha256 "
            "FROM source_files WHERE snapshot_id=?", (identity.snapshot_id,)
        ).fetchone()
    assert row[0] == 1 and row[1] == "physical.txt" and len(row[2]) == 64
    assert str(game) not in identity.policy_json
    assert "physical.txt" not in identity.policy_json
    reopened = SnapshotRepository(directory, game_root=game)
    reopened.activate(identity.snapshot_id, sources=(staged,))
    assert reopened.active_snapshot_id() == identity.snapshot_id


def test_r1_same_relative_target_under_different_game_root_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "game-first"
    second = tmp_path / "game-second"
    first.mkdir()
    second.mkdir()
    for root in (first, second):
        (root / "origin.txt").write_bytes(b"same")
    repo = SnapshotRepository(tmp_path / "data", game_root=first)
    old = repo.stage(
        (SourceFileInput("synthetic", "demo", "old.txt", b"old"),), _policy()
    ).snapshot_id
    repo.activate(old)
    staged = SourceFileInput("base", "demo", "origin.txt", b"same", live_path=first/"origin.txt")
    sid = repo.stage((staged,), _policy()).snapshot_id
    reopened = SnapshotRepository(tmp_path / "data", game_root=second)
    substituted = replace(staged, live_path=second/"origin.txt")
    with pytest.raises(SnapshotError) as exc:
        reopened.activate(sid, sources=(substituted,))
    assert exc.value.code == "SOURCE_CHANGED"
    assert reopened.active_snapshot_id() == old


@pytest.mark.parametrize("point", ["stage", "activation"])
def test_r1_symlink_target_cannot_be_bound_or_revalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str,
) -> None:
    import stellaris_supporter.storage.cache as cache_module

    game = tmp_path / "game"
    game.mkdir()
    original = game / "origin.txt"
    original.write_bytes(b"same")
    repo = SnapshotRepository(tmp_path / "data", game_root=game)
    old = repo.stage(
        (SourceFileInput("synthetic", "demo", "old.txt", b"old"),), _policy()
    ).snapshot_id
    repo.activate(old)
    source = SourceFileInput("base", "demo", "origin.txt", b"same", live_path=original)
    sid = snapshot_identity((source,), _policy()).snapshot_id
    if point == "activation":
        repo.stage((source,), _policy())
    # On Windows installations without symlink privileges, simulate lstat
    # reporting a reparse point rather than adding an intentional skip.
    target = game / "same-copy.txt"
    target.write_bytes(b"same")
    original.unlink()
    try:
        original.symlink_to(target)
    except OSError:
        original.write_bytes(b"same")
        original_check = cache_module._is_unsafe_link
        monkeypatch.setattr(
            cache_module, "_is_unsafe_link",
            lambda path: path == original or original_check(path),
        )
    with pytest.raises(SnapshotError) as exc:
        if point == "stage":
            repo.stage((source,), _policy())
        else:
            repo.activate(sid, sources=(source,))
    assert exc.value.code == "PATH_REJECTED"
    assert repo.active_snapshot_id() == old


def test_r1_duplicate_logical_source_ids_are_not_rescued_by_different_live_paths(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    a, b = game / "a.txt", game / "b.txt"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    repo = SnapshotRepository(tmp_path / "data", game_root=game)
    one = SourceFileInput("base", "same-id", "logical.txt", b"same", live_path=a)
    two = replace(one, live_path=b)
    with pytest.raises(SnapshotError) as exc:
        repo.stage((one, two), _policy())
    assert exc.value.code == "COLLISION_UNRESOLVED"
    assert repo.active_snapshot_id() is None


@pytest.mark.parametrize(
    ("value", "language"),
    [
        ("한글", "korean"),
        ("한글", "korean"),
        ("e\u0301", "english"),
    ],
    ids=["NFC-Korean", "NFD-Korean-Jamo", "Latin-combining"],
)
def test_r2_lossless_localisation_codepoints_bom_crlf_and_source_spans(
    tmp_path: Path, value: str, language: str,
) -> None:
    from stellaris_supporter.domain import SourceRef

    source_bytes = (
        b"\xef\xbb\xbf" + f'l_{language}:\r\n demo:0 "{value}"\r\n'.encode("utf-8")
    )
    source = SourceFileInput(
        "synthetic", "demo", f"localisation/{language}/demo.yml", source_bytes
    )
    repo = SnapshotRepository(tmp_path / "data")
    policy = _policy()
    sid = snapshot_identity((source,), policy).snapshot_id
    document = parse_localisation(source_bytes, _context(source, sid))
    assert document.complete and len(document.entries) == 1
    assert document.entries[0].raw_value == value
    repo.stage_from_results((source,), policy, localisation_documents=(document,))
    repo.activate(sid)
    stored = repo.localisation_entries()[0]
    assert list(map(ord, stored["raw_value"])) == list(map(ord, value))
    assert list(map(ord, stored["display_value"])) == list(map(ord, value))
    original = SourceRef(**stored["value_source_ref"])
    assert repo.source_bytes(original) == value.encode("utf-8")
    assert repo.cache.read(hashlib.sha256(source_bytes).hexdigest(), len(source_bytes)) == source_bytes
    with sqlite3.connect(repo.db_path) as conn:
        row = conn.execute(
            "SELECT raw_value,display_value FROM localisation_entries WHERE snapshot_id=?",
            (sid,),
        ).fetchone()
    assert row == (value, value)


def test_r2_raw_and_display_are_distinct_without_normalising_combining_marks(
    tmp_path: Path,
) -> None:
    from stellaris_supporter.domain import SourceRef

    raw = 'e\u0301\\"quoted'
    display = 'e\u0301"quoted'
    data = (f'l_english:\r\n demo:0 "{raw}"\r\n').encode("utf-8")
    src = SourceFileInput("synthetic", "demo", "localisation/english/demo.yml", data)
    repo = SnapshotRepository(tmp_path / "data")
    sid = snapshot_identity((src,), _policy()).snapshot_id
    doc = parse_localisation(data, _context(src, sid))
    assert doc.complete and doc.entries[0].raw_value == raw
    repo.stage_from_results((src,), _policy(), localisation_documents=(doc,))
    repo.activate(sid)
    stored = repo.localisation_entries()[0]
    assert stored["raw_value"] == raw
    assert stored["display_value"] == display
    assert repo.source_bytes(SourceRef(**stored["value_source_ref"])) == raw.encode("utf-8")


def test_r2_technology_raw_decomposed_unicode_roundtrip(tmp_path: Path) -> None:
    data = 'demo_tech = { cost = "e\u0301" }\n'.encode("utf-8")
    src = SourceFileInput("synthetic", "demo", "common/technology/nfd.txt", data)
    repo = SnapshotRepository(tmp_path / "data")
    sid = snapshot_identity((src,), _policy()).snapshot_id
    parsed = parse_bytes(data)
    adapted = adapt_technologies(parsed, data, _context(src, sid))
    assert adapted.complete and adapted.candidates
    repo.stage_from_results((src,), _policy(), technology_results=(adapted,))
    repo.activate(sid)
    candidate = repo.entities()[0]["candidate"]
    assert "e\u0301" in candidate["fields"][0]["raw_value"]
    from stellaris_supporter.domain import SourceRef

    assert repo.source_bytes(SourceRef(**candidate["source_ref"])) == data[
        candidate["source_ref"]["byte_start"]:candidate["source_ref"]["byte_end"]
    ]


def test_r2_identity_metadata_remains_nfc_strict() -> None:
    with pytest.raises(SnapshotError) as exc:
        snapshot_identity((), _policy(analysis_context={"name": "e\u0301"}))
    assert exc.value.code == "SCHEMA_ERROR"


def test_r3_policy_json_exact_byte_boundary_and_deterministic_sha() -> None:
    from stellaris_supporter.storage.identity import MAX_POLICY_JSON_BYTES

    baseline = _policy(analysis_context={"pad": ""})
    zero_bytes = len(canonical_json(baseline.identity_fields()))
    policy = _policy(analysis_context={"pad": "x" * (MAX_POLICY_JSON_BYTES-zero_bytes)})
    first = snapshot_identity((), policy)
    assert len(first.policy_json.encode("utf-8")) == MAX_POLICY_JSON_BYTES
    assert snapshot_identity((), policy).snapshot_id == first.snapshot_id
    assert snapshot_identity((), _policy()).snapshot_id != first.snapshot_id


def test_r3_over_budget_policy_rejected_before_db_insert_and_active_retained(
    tmp_path: Path,
) -> None:
    from stellaris_supporter.storage.identity import MAX_POLICY_JSON_BYTES

    repo = SnapshotRepository(tmp_path / "data")
    old = _seed_active(repo)
    baseline = _policy(analysis_context={"pad": ""})
    zero_bytes = len(canonical_json(baseline.identity_fields()))
    too_large = _policy(
        analysis_context={"pad": "x" * (MAX_POLICY_JSON_BYTES - zero_bytes + 1)}
    )
    with pytest.raises(SnapshotError) as exc:
        repo.stage((SourceFileInput("synthetic", "demo", "n.txt", b"small"),), too_large)
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert repo.active_snapshot_id() == old
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1


@pytest.mark.parametrize("failure", ["oversized-string", "nested", "item-count"])
def test_r3_policy_metadata_resource_limits(tmp_path: Path, failure: str) -> None:
    from stellaris_supporter.storage.identity import MAX_POLICY_JSON_BYTES

    if failure == "oversized-string":
        policy = _policy(dlc_state={"pad": "x" * (2 * MAX_POLICY_JSON_BYTES)})
    elif failure == "nested":
        context = {}
        for _ in range(40):
            context = {"child": context}
        policy = _policy(analysis_context=context)
    else:
        policy = _policy(analysis_context={f"k{i:04d}": i for i in range(5100)})
    with pytest.raises(SnapshotError) as error:
        snapshot_identity((), policy)
    assert error.value.code == "LIMIT_EXCEEDED"


def test_r4_schema_constraint_and_source_bytes_reject_cache_pointer_swap(
    tmp_path: Path,
) -> None:
    from stellaris_supporter.domain import SourceRef

    repo = SnapshotRepository(tmp_path / "data")
    files = (
        SourceFileInput("synthetic", "demo", "A.txt", b"AAAA"),
        SourceFileInput("synthetic", "demo", "B.txt", b"BBBB"),
    )
    sid = repo.stage(files, _policy()).snapshot_id
    repo.activate(sid)
    a_ref = SourceRef(
        snapshot_id=sid, source_kind="synthetic", source_id="demo",
        relative_path="A.txt", file_sha256=hashlib.sha256(b"AAAA").hexdigest(),
        byte_start=0, byte_end=4, line_start=1, line_end=1,
    )
    b_hash = hashlib.sha256(b"BBBB").hexdigest()
    assert repo.source_bytes(a_ref) == b"AAAA"
    with sqlite3.connect(repo.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE source_files SET cache_sha256=? "
                "WHERE snapshot_id=? AND relative_path='A.txt'",
                (b_hash, sid),
            )
        conn.rollback()
        # Deliberately bypass the CHECK to simulate a corrupt logical pointer.
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute(
            "UPDATE source_files SET cache_sha256=? "
            "WHERE snapshot_id=? AND relative_path='A.txt'",
            (b_hash, sid),
        )
    with pytest.raises(SnapshotError) as mismatch:
        repo.source_bytes(a_ref)
    assert mismatch.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() == sid
    assert repo.cache.read(b_hash, 4) == b"BBBB"


def test_r4_historical_valid_snapshot_remains_queryable_after_other_corruption(
    tmp_path: Path,
) -> None:
    from stellaris_supporter.domain import SourceRef

    repo = SnapshotRepository(tmp_path / "data")
    old_data = b"original"
    old = repo.stage(
        (SourceFileInput("synthetic", "demo", "old.txt", old_data),), _policy()
    ).snapshot_id
    repo.activate(old)
    new_files = (
        SourceFileInput("synthetic", "demo", "A.txt", b"AAAA"),
        SourceFileInput("synthetic", "demo", "B.txt", b"BBBB"),
    )
    newest = repo.stage(new_files, _policy()).snapshot_id
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute(
            "UPDATE source_files SET cache_sha256=? WHERE snapshot_id=? "
            "AND relative_path='A.txt'",
            (hashlib.sha256(b"BBBB").hexdigest(), newest),
        )
    ref = SourceRef(
        snapshot_id=old, source_kind="synthetic", source_id="demo",
        relative_path="old.txt", file_sha256=hashlib.sha256(old_data).hexdigest(),
        byte_start=0, byte_end=len(old_data), line_start=1, line_end=1,
    )
    assert repo.source_bytes(ref) == old_data
    with pytest.raises(SnapshotError) as exc:
        repo.activate(newest)
    assert exc.value.code in {"SCHEMA_ERROR", "SOURCE_CHANGED"}
    assert repo.active_snapshot_id() == old


def test_r5_adr_012_and_013_share_one_markdown_table() -> None:
    decisions = (Path(__file__).resolve().parents[1] / "docs" / "DECISIONS.md").read_text(
        encoding="utf-8"
    ).splitlines()
    previous = next(i for i, line in enumerate(decisions) if line.startswith("| ADR-012 |"))
    assert decisions[previous + 1].startswith("| ADR-013 |")
