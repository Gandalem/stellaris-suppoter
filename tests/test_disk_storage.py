"""Essential option-2 durability, negative dependencies and source-correctness checks."""

from __future__ import annotations

import hashlib
from threading import Event

import pytest

from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.comparison import DiffQuery, DiffService
from stellaris_supporter.config import Limits, Settings
from stellaris_supporter.domain import SourceContext
from stellaris_supporter.localisation.reader import parse_localisation
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository
from stellaris_supporter.storage.catalogue import FileCatalogue, index_lock


def fixture(tmp_path):
    game = tmp_path / "game"
    for folder in ("common/technology", "localisation/korean", "localisation/english"):
        (game / folder).mkdir(parents=True)
    (game / "common/technology/demo.txt").write_text("a={cost=100 prerequisites={b}}\nb={cost=1}")
    ko = game / "localisation/korean/demo.yml"
    en = game / "localisation/english/demo.yml"
    ko.write_text('l_korean:\n b:0 "기초"\n', encoding="utf-8")
    en.write_text(
        'l_english:\n a:0 "$shared$"\n shared:0 "Alpha"\n b:0 "Base"\n'
        + "".join(f' unused_{i}:0 "Unused {i}"\n' for i in range(1500)),
        encoding="utf-8",
    )
    settings = Settings(
        tmp_path / "config.toml", game, tmp_path / "private", "korean", False, Limits()
    )
    return settings, SnapshotRepository(settings.data_dir, game_root=game), ko, en


def search(repo, sid, text="a", language="korean"):
    service = SearchService(repo)
    try:
        return service.search(Query(text, snapshot_id=sid, language=language))
    finally:
        service.close()


def test_streaming_diagnostics_do_not_truncate_input():
    raw = ("l_english:\n" + "".join(f' key_{i}:0 "raw\\q"\n' for i in range(1500))).encode()
    context = SourceContext(
        "a" * 64,
        "synthetic",
        "demo",
        "localisation/english/test.yml",
        hashlib.sha256(raw).hexdigest(),
    )
    counts = {}
    seen = []
    doc = parse_localisation(
        raw,
        context,
        sink=lambda kind, value: seen.append(kind),
        diagnostic_counts=counts,
        game_compatibility=True,
    )
    assert seen.count("entry") == 1500
    assert counts["LOC_UNSUPPORTED_ESCAPE:warning"] == 1500
    assert not doc.entries
    assert len(doc.diagnostics) <= 3
    assert not any(d.code == "LIMIT_EXCEEDED" for d in doc.diagnostics)


def test_new_game_lexical_policy_preserves_raw_and_old_reader():
    raw = b'l_english:\n a:0 "A "quoted" name\\nSecond" # comment\n'
    context = SourceContext(
        "a" * 64,
        "synthetic",
        "demo",
        "localisation/english/test.yml",
        hashlib.sha256(raw).hexdigest(),
    )
    old = parse_localisation(raw, context)
    new = parse_localisation(raw, context, game_compatibility=True)
    assert not old.complete
    assert new.complete and len(new.entries) == 1
    assert new.entries[0].raw_value == 'A "quoted" name\\nSecond'
    assert new.entries[0].display_value == 'A "quoted" name\nSecond'
    assert new.entries[0].value_source_ref.raw_bytes(raw).decode() == new.entries[0].raw_value


def test_full_store_narrow_projection_negative_dependency_and_pinned_history(tmp_path, monkeypatch):
    settings, repo, ko, en = fixture(tmp_path)
    monkeypatch.setattr("stellaris_supporter.storage.repository.MAX_RECORDS", 1000)
    first = index_technologies(repo, settings)
    sid1 = first["snapshot_id"]
    assert first["storage"]["localisation_entries"] > 1500
    assert len(repo.localisation_entries(sid1)) < 30
    assert search(repo, sid1).results[0].display_name == "Alpha"
    ko.write_text('l_korean:\n a:0 "알파"\n b:0 "기초"\n', encoding="utf-8")
    second = index_technologies(repo, settings)
    sid2 = second["snapshot_id"]
    assert search(repo, sid2).results[0].display_name == "알파"
    assert search(repo, sid2, language="english").results[0].display_name == "Alpha"
    assert search(repo, sid1).results[0].display_name == "Alpha"
    assert second["processing"]["reused_files"] == 2
    assert second["processing"]["derived_reused"] > 0
    third = index_technologies(repo, settings)
    assert third["snapshot_id"] == sid2 and third["processing"]["parsed_files"] == 0
    ko.write_text('l_korean:\n a:0 "첫번째"\n a:0 "두번째"\n b:0 "기초"\n', encoding="utf-8")
    duplicate = index_technologies(repo, settings, allow_partial=True)
    entity = repo.entities(duplicate["snapshot_id"])[0]
    assert entity["localisation"]["resolution"] == "ambiguous"


def test_projection_is_reused_after_restart_and_rebuilt_if_corrupt(tmp_path, monkeypatch):
    settings, repo, _, _ = fixture(tmp_path)
    sid = index_technologies(repo, settings)["snapshot_id"]
    original = SearchService._new_index

    def forbidden(*args):
        raise AssertionError("Should reuse persistent index")

    monkeypatch.setattr(SearchService, "_new_index", forbidden)
    assert search(repo, sid).results
    monkeypatch.setattr(SearchService, "_new_index", original)
    cache = next((settings.data_dir / "search-projections").glob("*.sqlite3"))
    content = bytearray(cache.read_bytes())
    content[-1] ^= 1
    cache.write_bytes(content)
    assert search(repo, sid).results


def test_unrelated_translation_change_is_compared_and_source_only_changes_are_distinct(tmp_path):
    settings, repo, ko, en = fixture(tmp_path)
    sid1 = index_technologies(repo, settings)["snapshot_id"]
    en.write_text(
        en.read_text(encoding="utf-8").replace('"Unused 42"', '"Changed 42"'), encoding="utf-8"
    )
    sid2 = index_technologies(repo, settings)["snapshot_id"]
    response = DiffService(repo).compare(DiffQuery(sid1, sid2, game_id="unused_42"))
    assert response.status == "ok", response
    assert any(
        r["section"] == "localisation" and r["change_kind"] == "modified" for r in response.results
    )
    ko.write_text("# comment\n" + ko.read_text(encoding="utf-8"), encoding="utf-8")
    sid3 = index_technologies(repo, settings)["snapshot_id"]
    assert not DiffService(repo).compare(DiffQuery(sid2, sid3, kind="technology")).results
    assert (
        DiffService(repo)
        .compare(DiffQuery(sid2, sid3, kind="technology", include_source_changes=True))
        .results
    )


def test_cancel_retry_and_single_writer_preserve_active(tmp_path):
    settings, repo, ko, _ = fixture(tmp_path)
    sid = index_technologies(repo, settings)["snapshot_id"]
    ko.write_text('l_korean:\n a:0 "변경"\n b:0 "기초"\n', encoding="utf-8")
    cancel = Event()

    def progress(value):
        if value["phase"] == "parse":
            cancel.set()

    with pytest.raises(SnapshotError) as exc:
        index_technologies(repo, settings, cancel=cancel.is_set, progress=progress)
    assert exc.value.code == "CANCELLED" and repo.active_snapshot_id() == sid
    retried = index_technologies(repo, settings)
    assert retried["snapshot_id"] != sid
    with index_lock(settings.data_dir):
        with pytest.raises(SnapshotError) as busy:
            index_technologies(repo, settings)
        assert busy.value.code == "SQLITE_BUSY"
    store = FileCatalogue(repo)
    try:
        assert (
            store.conn.execute("SELECT count(*) FROM jobs WHERE status='cancelled'").fetchone()[0]
            == 1
        )
    finally:
        store.close()


def test_failed_unpublished_snapshot_can_retry_same_input(tmp_path, monkeypatch):
    settings, repo, _, _ = fixture(tmp_path)
    original = repo.stage_from_results

    def fail_after(*args, **kwargs):
        identity = original(*args, **kwargs)
        with repo._connection() as conn:
            conn.execute(
                "UPDATE snapshots SET status='failed' WHERE snapshot_id=?", (identity.snapshot_id,)
            )
        raise SnapshotError("SQLITE_WRITE_ERROR", "simulated")

    monkeypatch.setattr(repo, "stage_from_results", fail_after)
    with pytest.raises(SnapshotError):
        index_technologies(repo, settings)
    assert repo.active_snapshot_id() is None
    monkeypatch.setattr(repo, "stage_from_results", original)
    assert index_technologies(repo, settings)["activated"]


def test_encoding_corruption_cannot_be_accepted_as_partial(tmp_path):
    settings, repo, ko, _ = fixture(tmp_path)
    sid = index_technologies(repo, settings)["snapshot_id"]
    ko.write_bytes(b'l_korean:\n a:0 "\xff"\n')
    with pytest.raises(SnapshotError):
        index_technologies(repo, settings, allow_partial=True)
    assert repo.active_snapshot_id() == sid


def test_foreign_catalogue_is_rejected_without_mutation(tmp_path):
    import sqlite3

    settings, repo, _, _ = fixture(tmp_path)
    path = settings.data_dir / "localisation-products.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE unrelated(value TEXT)")
    connection.commit()
    connection.close()
    original = path.read_bytes()
    with pytest.raises(SnapshotError):
        FileCatalogue(repo)
    assert path.read_bytes() == original


def test_corrupt_file_product_is_rebuilt_from_original(tmp_path):
    settings, repo, _, _ = fixture(tmp_path)
    first = index_technologies(repo, settings)
    store = FileCatalogue(repo)
    store.conn.execute("UPDATE entries SET display='forged' WHERE key='a'")
    store.close()
    second = index_technologies(repo, settings)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert search(repo, second["snapshot_id"]).results[0].display_name == "Alpha"


def test_search_keeps_previous_snapshot_while_background_index_runs(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    settings, repo, ko, _ = fixture(tmp_path)
    before = index_technologies(repo, settings)["snapshot_id"]
    ko.write_text('l_korean:\n a:0 "새 이름"\n b:0 "기초"\n', encoding="utf-8")
    paused, release = Event(), Event()

    def progress(value):
        if value["phase"] == "parse" and not paused.is_set():
            paused.set()
            if not release.wait(15):
                raise AssertionError("Foreground query did not release index")

    def run():
        separate = SnapshotRepository(settings.data_dir, game_root=settings.game_root)
        return index_technologies(separate, settings, progress=progress)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(run)
        try:
            assert paused.wait(15)
            assert repo.active_snapshot_id() == before
            assert search(repo, before).results[0].display_name == "Alpha"
        finally:
            release.set()
        after = pending.result(timeout=30)["snapshot_id"]
    assert after != before
    assert repo.active_snapshot_id() == after
    assert search(repo, after).results[0].display_name == "새 이름"
    assert search(repo, before).results[0].display_name == "Alpha"
