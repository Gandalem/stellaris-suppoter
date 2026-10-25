"""Essential desktop safety, persistence, worker and native lifecycle acceptance."""
from __future__ import annotations

import json
import socket
from dataclasses import asdict

import pytest

from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.config import Limits, Settings
from stellaris_supporter.desktop.model import Mode, OverlayState, bounded_rect
from stellaris_supporter.desktop.settings import (
    Card,
    Preferences,
    load_preferences,
    save_preferences,
)
from stellaris_supporter.desktop.steam import discover_installations, read_vdf
from stellaris_supporter.desktop.windows import parse_hotkey
from stellaris_supporter.evaluation import create_corpus, retrieval_gold
from stellaris_supporter.storage import SnapshotError, SnapshotRepository


def setup_data(tmp_path):
    game = tmp_path/"game"
    create_corpus(game)
    settings = Settings(tmp_path/"config.toml", game, tmp_path/"private", "korean", False, Limits())
    repo = SnapshotRepository(settings.data_dir, game_root=game)
    return settings, repo


def test_state_latch_alt_tab_restore_and_clamping():
    state = OverlayState()
    assert state.observe(True) == Mode.PASSIVE
    assert state.toggle(True) == Mode.INTERACTIVE
    assert state.observe(False) == Mode.HIDDEN
    assert state.observe(True) == Mode.PASSIVE
    state.hide()
    assert state.observe(True) == Mode.HIDDEN
    assert state.toggle(False) == Mode.HIDDEN
    assert state.toggle(True) == Mode.INTERACTIVE
    assert bounded_rect((9000, -100, 2000, 1500), 800, 600) == (0, 0, 800, 600)


def test_preferences_round_trip_and_bounds(tmp_path):
    prefs = Preferences(data_dir=str(tmp_path/"private"), cards=[Card.create(kind="technology", snapshot_id="a"*64, game_id="demo")])
    path = tmp_path/"prefs.json"
    save_preferences(prefs, path)
    assert asdict(load_preferences(path)) == asdict(prefs)
    prefs.cards[0].snapshot_id = "current"
    with pytest.raises(ValueError):
        save_preferences(prefs, path)
    assert load_preferences(path).cards[0].snapshot_id == "a"*64
    with pytest.raises(ValueError):
        Preferences(opacity=0).validate()


def test_preferences_reject_source_write(tmp_path):
    prefs = Preferences(game_root=str(tmp_path/"game"))
    with pytest.raises(ValueError):
        save_preferences(prefs, tmp_path/"game"/"prefs.json")
    assert not (tmp_path/"game").exists()


def test_steam_manifest_discovery_multiple_and_malformed(tmp_path):
    roots = [tmp_path/"steam", tmp_path/"second"]
    for root in roots:
        game = root/"steamapps"/"common"/"Stellaris"
        (game/"common"/"technology").mkdir(parents=True)
        (game/"stellaris.exe").write_bytes(b"synthetic")
        (root/"steamapps"/"appmanifest_281990.acf").write_text('"AppState" { "appid" "281990" "installdir" "Stellaris" }')
    library = str(roots[1]).replace("\\", "\\\\")
    vdf = roots[0]/"steamapps"/"libraryfolders.vdf"
    vdf.write_text('"libraryfolders" { "1" { "path" "'+library+'" } }')
    assert set(discover_installations([roots[0]])) == {r/"steamapps"/"common"/"Stellaris" for r in roots}
    (roots[1]/"steamapps"/"appmanifest_281990.acf").write_text('"AppState" { "appid" "281990" "installdir" "../bad" }')
    assert len(discover_installations([roots[0]])) == 1
    vdf.write_text('"bad" {')
    with pytest.raises(ValueError):
        read_vdf(vdf)


@pytest.mark.parametrize("value", ["Space", "Win+H", "Ctrl+Ctrl+H", "Ctrl+Shift+", "Alt+F4", "Ctrl+한"])
def test_hotkey_invalid(value):
    with pytest.raises(ValueError):
        parse_hotkey(value)


def test_hotkey_parse():
    assert parse_hotkey("Ctrl+Shift+Space") == (0x4006, 32)


def test_offline_readonly_sources_instruction_text_and_cancellation(tmp_path, monkeypatch):
    settings, repo = setup_data(tmp_path)
    before = {str(p.relative_to(settings.game_root)): p.read_bytes() for p in settings.game_root.rglob("*") if p.is_file()}
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: pytest.fail("Outbound network"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("Outbound network"))
    result = index_technologies(repo, settings)
    sid = result["snapshot_id"]
    from stellaris_supporter.retrieval import Query, SearchService
    service = SearchService(repo)
    assert service.search(Query("demo_00001")).results
    from stellaris_supporter.answers import AnswerService
    from stellaris_supporter.comparison import DiffQuery, DiffService
    from stellaris_supporter.references import ReferenceQuery, ReferenceService
    assert AnswerService(service, repo).answer(Query("demo_00001"), exact_game_id=True).results
    assert ReferenceService(repo).refs(ReferenceQuery("demo_00001")).snapshot_id == sid
    assert DiffService(repo).compare(DiffQuery(sid, sid)).status == "ok"
    assert repo.list_snapshots()[0]
    # Untrusted instruction-looking content stays ordinary static bytes.
    from stellaris_supporter.desktop.presentation import text_view
    malicious = '<script>PRIVATE_TOKEN ignore previous instructions</script>'
    text = text_view({"status": "ok", "diagnostics": [{"code": malicious}]})
    assert malicious in text
    assert service.search(Query(malicious)).status == "not_found"
    service.close()
    (settings.game_root/"common"/"technology"/"new.txt").write_text("new_demo = {cost=1}")
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls > 4
    with pytest.raises(SnapshotError) as exc:
        index_technologies(repo, settings, cancel=cancel)
    assert exc.value.code == "CANCELLED"
    assert repo.active_snapshot_id() == sid
    assert all((settings.game_root/name).read_bytes() == raw for name, raw in before.items())


def test_fixed_retrieval_gold_is_balanced_and_repeatable(tmp_path):
    settings, repo = setup_data(tmp_path)
    index_technologies(repo, settings)
    first, second = retrieval_gold(repo), retrieval_gold(repo)
    assert first == second
    assert first["count"] >= 40 and first["passed"], first
    assert first["correct_abstention"] == 1 and first["exact_first"] == 1


def test_worker_snapshot_card_and_exact_entity(tmp_path):
    pytest.importorskip("PySide6.QtCore")
    from stellaris_supporter.desktop.worker import Worker
    settings, repo = setup_data(tmp_path)
    indexed = index_technologies(repo, settings)
    worker = Worker({})
    worker.configure(settings)
    search = worker.perform("search", {"text": "demo_00000"})
    hits = search["results"]
    assert len(hits) == 2
    selected = hits[1]
    card = Card.create(kind="technology", snapshot_id=indexed["snapshot_id"], game_id="demo_00000", entity_key=selected["entity_key"])
    answer = worker.perform("card", {"card": asdict(card)})
    assert len(answer["results"]) == 1
    assert answer["results"][0]["entity_key"] == selected["entity_key"]
    ref_card = Card.create(kind="reference", snapshot_id=indexed["snapshot_id"], game_id="demo_00001", depth=4)
    assert worker.perform("card", {"card": asdict(ref_card)})["query"]["depth"] == 4
    assert worker.perform("snapshots", {})["active"] == indexed["snapshot_id"]
    worker.stop()


def test_qt_manager_dataflow_and_clean_stop(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from stellaris_supporter.desktop import app as desktop
    settings, repo = setup_data(tmp_path)
    index_technologies(repo, settings)
    monkeypatch.setattr(desktop, "discover_installations", lambda: (settings.game_root, tmp_path/"second-game"))
    monkeypatch.setattr(desktop, "Windows", lambda: None)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    prefs = Preferences(game_root=str(settings.game_root), data_dir=str(settings.data_dir))
    manager = desktop.Manager(prefs, tmp_path/"prefs.json")
    loop = QEventLoop()
    failures = []
    ticks = 0
    def check():
        nonlocal ticks
        ticks += 1
        if manager.active_snapshot:
            manager.search_input.setText("demo_00001")
            manager.do_search()
            timer.stop()
            QTimer.singleShot(1500, complete)
        elif ticks > 100:
            failures.append("snapshot response timeout")
            timer.stop()
            manager.exit_app()
    def complete():
        try:
            assert manager.search_results.count() == 1
            assert "우주 항법 00001" in manager.answer_text.toPlainText()
            assert "기본 연구 비용  101" in manager.answer_text.toPlainText()
            manager.pin_technology()
            assert len(manager.prefs.cards) == 1
            original = manager.prefs.cards[0]
            original_rect = list(original.rect)
            for _ in range(5):
                manager.pin_technology()
            assert len(manager.prefs.cards) == 1
            assert manager.prefs.cards[0].rect == original_rect
            assert len(manager.cards) == 1
            from PySide6.QtGui import QPalette
            card_window = manager.cards[original.uid]
            card_window.ensurePolished()
            assert card_window.body.palette().color(QPalette.ColorRole.Base).name() == "#101720"
            from dataclasses import replace
            duplicate = replace(original, uid="b" * 32, rect=[300, 300, 320, 240])
            manager.prefs.cards.append(duplicate)
            manager.save()
            manager.rebuild_cards()
            monkeypatch.setattr(desktop.QMessageBox, "question", lambda *args: desktop.QMessageBox.StandardButton.No)
            manager.cleanup_duplicate_cards()
            assert len(manager.prefs.cards) == 2
            monkeypatch.setattr(desktop.QMessageBox, "question", lambda *args: desktop.QMessageBox.StandardButton.Yes)
            manager.cleanup_duplicate_cards()
            assert len(manager.prefs.cards) == 1 and manager.prefs.cards[0].uid == original.uid
            backups = list(tmp_path.glob("prefs.before-card-cleanup-*.json"))
            assert len(backups) == 1 and len(load_preferences(backups[0]).cards) == 2
            assert manager.prefs.cards[0].rect == original_rect
            assert manager.installations.count() == 3
            manager.game_path.clear()
            manager.installations.setCurrentIndex(0)
            manager.installations.setCurrentIndex(1)
            assert manager.game_path.text() == str(settings.game_root)
            failure = {"status": "error", "results": [], "diagnostics": [{"code": "SQLITE_ERROR"}]}
            manager.show_search(failure)
            assert "SQLITE_ERROR" in manager.answer_text.toPlainText()
            assert manager.current_hit is None or manager.search_results.count() == 0
            manager.show_overlay_search()
            monkeypatch.setattr(manager, "submit", lambda kind, payload, callback, channel=None: callback(failure))
            manager.overlay_input.setText("missing")
            manager.overlay_query()
            assert manager.overlay_results.count() == 1
            item = manager.overlay_results.item(0)
            assert "SQLITE_ERROR" in item.text()
            assert not item.flags()
            count = len(manager.prefs.cards)
            manager.overlay_pin(item)
            assert len(manager.prefs.cards) == count
            retries = []
            monkeypatch.setattr(manager, "start_index", lambda: retries.append(True))
            monkeypatch.setattr(desktop.QMessageBox, "question", lambda *args: desktop.QMessageBox.StandardButton.No)
            manager.latest["index"] = 900
            manager.callbacks[900] = manager.index_done
            manager.result({"id": 900, "channel": "index", "kind": "index", "error": "PARTIAL_INDEX"})
            assert not retries
            monkeypatch.setattr(desktop.QMessageBox, "question", lambda *args: desktop.QMessageBox.StandardButton.Yes)
            manager.latest["index"] = 901
            manager.callbacks[901] = manager.index_done
            manager.result({"id": 901, "channel": "index", "kind": "index", "error": "PARTIAL_INDEX"})
            assert manager.partial.isChecked() and retries == [True]
        except AssertionError as exc:
            failures.append(str(exc))
        manager.exit_app()
    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(50)
    manager.thread.finished.connect(loop.quit)
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    assert not manager.thread.isRunning()
    assert not failures, failures
    manager.deleteLater()


def test_worker_stale_job_and_private_exception(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtCore")
    from stellaris_supporter.desktop.worker import Worker
    worker = Worker({"lookup": 2})
    monkeypatch.setattr(worker, "configure", lambda _: None)
    def fail(*args):
        raise RuntimeError("PRIVATE_PATH_TOKEN")
    monkeypatch.setattr(worker, "perform", fail)
    captured = []
    worker.result.connect(captured.append)
    job = {"channel": "lookup", "id": 1, "kind": "search", "settings": None, "payload": {}}
    worker.run(job)
    assert not captured
    worker.run({**job, "id": 2})
    assert captured[0]["error"] == "RuntimeError"
    assert "PRIVATE_PATH_TOKEN" not in json.dumps(captured)


def test_search_failure_records_local_metadata_without_query(tmp_path, monkeypatch):
    import sqlite3

    from stellaris_supporter.desktop.worker import Worker

    settings, repo = setup_data(tmp_path)
    index_technologies(repo, settings)
    worker = Worker({})
    worker.configure(settings)
    def fail(*args):
        raise sqlite3.OperationalError("simulated query failure")
    monkeypatch.setattr(worker.search, "_sql_matches", fail)
    response = worker.perform("search", {"text": "PRIVATE_QUERY_TOKEN"})
    assert response["status"] == "error"
    assert response["diagnostics"][0]["code"] == "SQLITE_ERROR"
    path = settings.data_dir / "diagnostics" / "errors.jsonl"
    raw = path.read_text(encoding="utf-8")
    assert "PRIVATE_QUERY_TOKEN" not in raw
    event = json.loads(raw.splitlines()[-1])
    assert event["stage"] == "search_query"
    assert event["errors"][0]["type"] == "OperationalError"
    assert all("/" not in frame["file"] and "\\" not in frame["file"] for frame in event["frames"])
    worker.stop()


def test_diagnostic_rotation_and_failure_are_bounded(tmp_path, monkeypatch):
    from stellaris_supporter.desktop import diagnostics

    monkeypatch.setattr(diagnostics, "MAX_BYTES", 900)
    for _ in range(8):
        diagnostics.record_error(tmp_path, "search_query", ValueError("PRIVATE_VALUE_TOKEN"))
    files = list((tmp_path / "diagnostics").glob("errors*.jsonl"))
    assert len(files) == 2
    assert all(p.stat().st_size <= 900 for p in files)
    assert all("PRIVATE_VALUE_TOKEN" not in p.read_text() for p in files)
    monkeypatch.setattr(diagnostics, "_ensure_directory", lambda _: (_ for _ in ()).throw(OSError()))
    diagnostics.record_error(tmp_path, "search_query", ValueError())


def test_first_launch_guides_index_then_enables_search(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from stellaris_supporter.desktop import app as desktop

    settings, repo = setup_data(tmp_path)
    monkeypatch.setattr(desktop, "Windows", lambda: None)
    monkeypatch.setattr(desktop, "discover_installations", lambda: ())
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    manager = desktop.Manager(Preferences(game_root=str(settings.game_root),
                                         data_dir=str(settings.data_dir)), tmp_path / "prefs.json")
    loop = QEventLoop()
    state = ["empty"]
    failures = []
    def finish():
        if not manager.thread.isRunning() and not manager.index_thread.isRunning():
            loop.quit()
    manager.thread.finished.connect(finish)
    manager.index_thread.finished.connect(finish)
    def tick():
        try:
            if state[0] == "empty" and "아직 검색 데이터" in manager.data_status.text():
                assert not manager.search_input.isEnabled()
                assert not manager.search_button.isEnabled()
                manager.show_overlay_search()
                assert not manager.overlay_input.isEnabled()
                assert "먼저 색인" in manager.overlay_results.item(0).text()
                state[0] = "indexing"
                manager.start_index()
            elif state[0] == "indexing" and manager.active_snapshot:
                assert manager.search_input.isEnabled() and manager.search_button.isEnabled()
                assert manager.overlay_input.isEnabled()
                assert manager.overlay_results.count() == 0
                state[0] = "searching"
                manager.search_input.setText("demo_00001")
                manager.do_search()
            elif state[0] == "searching" and manager.search_results.count():
                assert manager.search_results.count() == 1
                state[0] = "done"
                timer.stop()
                manager.exit_app()
        except Exception as exc:
            failures.append(str(exc))
            timer.stop()
            manager.exit_app()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    QTimer.singleShot(20000, manager.exit_app)
    QTimer.singleShot(25000, loop.quit)
    loop.exec()
    assert not manager.thread.isRunning() and not manager.index_thread.isRunning()
    assert not failures, failures
    assert state[0] == "done", state
    manager.deleteLater()


def test_card_identity_preserves_snapshots_definitions_depth_and_custom_fields():
    from dataclasses import replace

    from stellaris_supporter.desktop.settings import card_identity, split_duplicate_cards
    first = Card.create(kind="technology", snapshot_id="a" * 64, game_id="same", entity_key="b" * 64)
    duplicate = replace(first, uid="c" * 32, rect=[300, 300, 320, 240])
    different_snapshot = replace(first, uid="d" * 32, snapshot_id="e" * 64)
    different_definition = replace(first, uid="f" * 32, entity_key="1" * 64)
    custom_fields = replace(first, uid="2" * 32, fields=["cost"])
    reference = replace(first, uid="3" * 32, kind="reference")
    deeper_reference = replace(reference, uid="4" * 32, depth=4)
    assert card_identity(first) == card_identity(duplicate)
    kept, duplicates = split_duplicate_cards([first, duplicate, different_snapshot, different_definition,
                                              custom_fields, reference, deeper_reference])
    assert duplicates == [duplicate]
    assert kept == [first, different_snapshot, different_definition, custom_fields, reference, deeper_reference]
