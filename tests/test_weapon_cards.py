"""Essential weapon card option 2 persistence, data, lifecycle and stale UI checks."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from test_weapons import fixture

from stellaris_supporter.desktop.model import place_card
from stellaris_supporter.desktop.settings import (
    Card,
    Preferences,
    PreferencesStore,
    load_preferences,
    save_preferences,
)
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.weapon_cards import DEFAULT_FIELDS, project, summary_text


@contextmanager
def desktop_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from stellaris_supporter.desktop import app as desktop
    from stellaris_supporter.desktop.worker import Worker

    settings, repo, sid, text, table = fixture(tmp_path)
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    for name in ("malgun.ttf", "segoeui.ttf"):
        font = Path("C:/Windows/Fonts") / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    monkeypatch.setattr(desktop, "Windows", lambda: None)
    monkeypatch.setattr(desktop.Manager, "initialise", lambda self: None)
    prefs = Preferences(game_root=str(settings.game_root), data_dir=str(settings.data_dir))
    manager = desktop.Manager(prefs, tmp_path / "desktop.json")
    manager.timer.stop()
    manager.active_snapshot = sid
    worker = Worker({})
    worker.configure(settings)
    calls = []

    def submit(kind, payload, callback, channel=None):
        calls.append((kind, payload))
        callback(worker.perform(kind, payload))

    monkeypatch.setattr(manager, "submit", submit)
    try:
        yield manager, worker, sid, (settings, repo, text, table), calls, desktop
    finally:
        worker.stop()
        manager.exiting = True
        manager.timer.stop()
        manager.hide()
        for window in manager.cards.values():
            window.hide()
        manager.bus.stop.emit()
        manager.index_bus.stop.emit()
        for thread in (manager.thread, manager.index_thread):
            for _ in range(100):
                application.processEvents()
                if not thread.isRunning():
                    break
                thread.wait(20)
        manager.tray.hide()
        manager.allow_close = True
        manager.close()


def weapon(sid="a" * 64):
    return Card.create(
        kind="weapon", snapshot_id=sid, game_id="SMALL_BLUE_LASER", entity_key="b" * 64
    )


def test_mixed_preferences_backup_and_restore(tmp_path):
    path = tmp_path / "desktop.json"
    tech = Card.create(kind="technology", snapshot_id="a" * 64, game_id="tech")
    prefs = Preferences(cards=[tech])
    save_preferences(prefs, path)
    original = path.read_bytes()
    loaded = load_preferences(path)
    store = PreferencesStore(path, loaded)
    new = weapon()
    assert new.fields == DEFAULT_FIELDS and new.domain == "component_template"
    store.save(replace(loaded, cards=[tech, new]))
    assert store.backup.read_bytes() == original
    assert asdict(load_preferences(path)) == asdict(replace(loaded, cards=[tech, new]))
    backups = list(tmp_path.glob("*.before-weapons-*.json"))
    store.save(replace(loaded, cards=[new]))
    assert list(tmp_path.glob("*.before-weapons-*.json")) == backups
    assert json.loads(original)["cards"][0]["fields"] == ["area", "tier", "cost", "prerequisites"]
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["cards"][0]["fields"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_preferences(path).cards[0].fields == DEFAULT_FIELDS


def test_external_writer_and_live_lock_preserve_settings(tmp_path):
    from PySide6.QtCore import QLockFile

    path = tmp_path / "desktop.json"
    prefs = Preferences()
    save_preferences(prefs, path)
    a = PreferencesStore(path, load_preferences(path))
    b = PreferencesStore(path, load_preferences(path))
    a.save(replace(prefs, opacity=80))
    good = path.read_bytes()
    with pytest.raises(SnapshotError) as exc:
        b.save(replace(prefs, opacity=70))
    assert exc.value.code == "PREFERENCES_CHANGED" and path.read_bytes() == good
    lock = QLockFile(str(path) + ".write.lock")
    assert lock.tryLock(0)
    try:
        with pytest.raises(SnapshotError) as exc:
            a.save(prefs)
        assert exc.value.code == "PREFERENCES_BUSY" and path.read_bytes() == good
    finally:
        lock.unlock()


def test_backup_failure_does_not_add_new_card(tmp_path, monkeypatch):
    path = tmp_path / "desktop.json"
    prefs = Preferences()
    save_preferences(prefs, path)
    original = path.read_bytes()
    store = PreferencesStore(path, load_preferences(path))
    real_open = Path.open

    def fail_backup(self, *args, **kwargs):
        if ".before-weapons-" in self.name:
            raise PermissionError("Synthetic backup failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_backup)
    with pytest.raises(PermissionError):
        store.save(replace(prefs, cards=[weapon()]))
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "change",
    [
        {"domain": "technology"},
        {"entity_key": None},
        {"fields": ["cost", "cost"]},
        {"kind": "reference"},
        {"fields": ["unknown"]},
    ],
)
def test_weapon_settings_are_typed(change):
    with pytest.raises(ValueError):
        Preferences(cards=[replace(weapon(), **change)]).validate()


def test_place_cards_uses_free_space_then_bounds_fallback():
    original = [24, 24, 360, 300]
    existing = [original]
    placed = place_card([24, 24, 360, 300], existing, 1280, 720, original)
    assert placed[0] >= 384 and original == [24, 24, 360, 300]
    crowded = place_card([24, 24, 360, 300], [[0, 0, 800, 600]] * 24, 800, 600)
    assert 0 <= crowded[0] <= 440 and 0 <= crowded[1] <= 300


def test_weapon_pin_connections_dedup_and_unpin_preserve_other_window(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, calls, desktop):
        browser = manager.weapon_browser
        browser.open_weapon({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"})
        browser.pin_weapon()
        card = manager.prefs.cards[0]
        assert card.kind == "weapon" and card.fields == DEFAULT_FIELDS
        original_window = manager.cards[card.uid]
        assert "8–21" in original_window.summary.accessibleName()
        assert "제작 비용 · 합금  13" in original_window.summary.accessibleName()
        assert "999" not in original_window.summary.accessibleName()
        browser.pin_weapon()
        assert len(manager.prefs.cards) == 1 and "고정됨" in browser.weapon_pin.text()
        manager.open_card_detail(card.uid, connections=True)
        assert (
            browser.link_list.currentRow() == 0 and browser.current["payload"]["snapshot_id"] == sid
        )
        for kind in ("technology", "component_template"):
            item = next(
                browser.link_list.item(i)
                for i in range(browser.link_list.count())
                if browser.link_list.item(i).data(256)["kind"] == kind
            )
            browser.link_list.setCurrentItem(item)
            browser.pin_link()
        assert len(manager.prefs.cards) == 3
        assert manager.cards[card.uid] is original_window
        assert sum(kind == "card" for kind, p in calls) == 3
        restored = load_preferences(tmp_path / "desktop.json")
        assert [asdict(c) for c in restored.cards] == [asdict(c) for c in manager.prefs.cards]
        other = manager.prefs.cards[-1]
        other_window = manager.cards[other.uid]
        manager.remove_card_uid(card.uid)
        assert len(manager.prefs.cards) == 2 and manager.cards[other.uid] is other_window
        assert card.uid not in manager.cards
        manager.state.hide()
        manager.pin(manager.prefs.cards[0])
        assert manager.state.enabled is False


def test_card_failure_stale_responses_and_save_failure(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, _, desktop):
        manager.pin_entity(
            "component_template", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        card = manager.prefs.cards[0]
        queued = []
        monkeypatch.setattr(
            manager,
            "submit",
            lambda kind, p, callback, channel=None: queued.append((kind, p, callback)),
        )
        manager.refresh_card_data([card.uid])
        old = queued[-1]
        window = manager.cards[card.uid]
        manager.prefs.language = "english"
        window.data = None
        old[2](worker.perform(old[0], old[1]))
        assert window.data is None
        manager.prefs.language = "korean"
        manager.show_card(
            card.uid, {"status": "error", "card_request": worker.card_request(asdict(card))}
        )
        assert not window.summary.isVisible() and "자료 읽기 실패" in window.body.toPlainText()
        monkeypatch.setattr(manager, "save", lambda candidate=None: False)
        manager.remove_card_uid(card.uid)
        assert card.uid in manager.cards and len(manager.prefs.cards) == 1
        with pytest.raises(SnapshotError):
            worker.perform("card", {"card": {**asdict(card), "kind": "alien"}})


def test_summary_complete_numbers_small_card_and_hidden_count(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, _, desktop):
        from stellaris_supporter.desktop.weapon_card import WeaponSummary

        detail = worker.perform(
            "weapon_detail", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        view = project(detail)
        summary = WeaponSummary()
        summary.set_data(view, DEFAULT_FIELDS)
        lines = summary.rows(400, 250)
        assert any("8–21" in line for line in lines) and any("90.0%" in line for line in lines)
        assert any("합금" in line and "13" in line for line in lines)
        assert not any("…" in line for line in lines if "8–21" in line)
        view["fields"]["damage"]["text"] = "1234567890" * 6
        summary.set_data(view, ["damage"])
        lines = summary.rows(180, 160)
        assert not any("1234567890" in line for line in lines)
        assert any("추가 1항목" in line for line in lines)
        summary.set_data(view, ["accuracy", "tracking"])
        lines = summary.rows(350, summary.fontMetrics().lineSpacing() * 2)
        assert any("추가 2항목" in line for line in lines)
        assert "추가 조건" in summary_text(view, [])


def test_update_preview_cancel_changed_context_and_success(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (
        manager,
        worker,
        sid,
        (settings, repo, text, table),
        calls,
        desktop,
    ):
        from stellaris_supporter.cli_index import index_technologies

        manager.pin_entity(
            "component_template", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        old = manager.prefs.cards[0]
        original_window = manager.cards[old.uid]
        original_rect = list(old.rect)
        table.write_bytes(table.read_bytes().replace(b";8;21;", b";9;22;"))
        new_sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]

        def change_context(*args):
            manager.prefs.language = "english"
            return desktop.QMessageBox.StandardButton.Yes

        monkeypatch.setattr(desktop, "plain_question", change_context)
        manager.update_weapon_card(old, new_sid)
        assert manager.prefs.cards[0].snapshot_id == sid
        manager.prefs.language = "korean"
        monkeypatch.setattr(
            desktop, "plain_question", lambda *args: desktop.QMessageBox.StandardButton.Cancel
        )
        manager.update_weapon_card(old, new_sid)
        assert manager.prefs.cards[0].snapshot_id == sid
        monkeypatch.setattr(
            desktop, "plain_question", lambda *args: desktop.QMessageBox.StandardButton.Yes
        )
        manager.update_weapon_card(old, new_sid)
        current = manager.prefs.cards[0]
        assert (
            current.uid == old.uid
            and current.snapshot_id == new_sid
            and current.rect == original_rect
        )
        assert manager.cards[current.uid] is original_window
        assert "9–22" in manager.cards[current.uid].summary.accessibleName()
        assert current.fields == old.fields


def test_pending_pin_context_and_shared_card_limit(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, _, desktop):
        queued = []
        monkeypatch.setattr(
            manager,
            "submit",
            lambda kind, p, callback, channel=None: queued.append((kind, p, callback)),
        )
        payload = {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        manager.pin_entity("component_template", payload)
        manager.pin_entity("component_template", payload)
        assert len(queued) == 1
        manager.settings_epoch += 1
        queued[0][2](worker.perform(queued[0][0], queued[0][1]))
        assert manager.prefs.cards == [] and manager.pending_pins == set()
        manager.prefs.cards = [
            Card.create(kind="technology", snapshot_id=sid, game_id=f"demo_{i}") for i in range(24)
        ]
        manager.rebuild_cards()
        original = dict(manager.cards)
        manager.pin(weapon(sid))
        assert len(manager.prefs.cards) == 24 and manager.cards == original
        assert not (tmp_path / "desktop.json").exists()


def test_update_rechecks_preview_and_does_not_merge_collision(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (
        manager,
        worker,
        sid,
        (settings, repo, text, table),
        _,
        desktop,
    ):
        from stellaris_supporter.cli_index import index_technologies

        manager.pin_entity(
            "component_template", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        old = manager.prefs.cards[0]
        table.write_bytes(table.read_bytes().replace(b";8;21;", b";9;22;"))
        new_sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
        previews = []

        def changing(kind, payload, callback, channel=None):
            data = worker.perform(kind, payload)
            if kind == "card_preview":
                previews.append(data)
                if len(previews) == 2:
                    data["after"]["summary"]["name"] += "changed"
            callback(data)

        monkeypatch.setattr(manager, "submit", changing)
        monkeypatch.setattr(
            desktop, "plain_question", lambda *a: desktop.QMessageBox.StandardButton.Yes
        )
        manager.update_weapon_card(old, new_sid)
        assert len(previews) == 2 and manager.prefs.cards[0].snapshot_id == sid
        monkeypatch.setattr(
            manager, "submit", lambda kind, p, cb, channel=None: cb(worker.perform(kind, p))
        )
        manager.pin_entity("component_template", {"snapshot_id": new_sid, "game_id": old.game_id})
        manager.update_weapon_card(old, new_sid)
        assert len(manager.prefs.cards) == 2 and manager.prefs.cards[0].snapshot_id == sid


def test_passive_flags_and_native_geometry_scale_once(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import Qt

    from stellaris_supporter.desktop.model import Mode

    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, _, desktop):
        manager.pin_entity(
            "component_template", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        card = manager.prefs.cards[0]
        window = manager.cards[card.uid]
        positions = []
        passive = []
        manager.native = SimpleNamespace(
            user=SimpleNamespace(SetWindowPos=lambda *args: positions.append(args)),
            passive=lambda hwnd, value: passive.append(value),
        )
        target = SimpleNamespace(rect=(120, 90, 1920, 1080), dpi=144)
        before = list(card.rect)
        window.present(Mode.PASSIVE, target)
        assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert window.actions.isHidden() and passive[-1] is True
        assert positions[-1][2:6] == (
            120 + round(card.rect[0] * 1.5),
            90 + round(card.rect[1] * 1.5),
            540,
            450,
        )
        window.present(Mode.INTERACTIVE, target)
        assert not window.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert not window.actions.isHidden() and passive[-1] is False
        window.present(Mode.HIDDEN, None)
        assert not window.isVisible() and card.rect == before


def test_edit_menu_is_owned_but_unrelated_foreground_still_hides(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMenu

    from stellaris_supporter.desktop.model import Mode

    with desktop_fixture(tmp_path, monkeypatch) as (manager, worker, sid, _, _, desktop):
        manager.pin_entity(
            "component_template", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        window = next(iter(manager.cards.values()))
        window.show()
        menu = window.findChildren(QMenu)[0]
        menu.show()
        manager.target = SimpleNamespace(hwnd=123)
        manager.state.mode = Mode.INTERACTIVE
        manager.native = SimpleNamespace(foreground=lambda: int(menu.winId()))
        assert manager.eligible()
        manager.native = SimpleNamespace(foreground=lambda: 987654321)
        assert not manager.eligible()
        manager.state.mode = Mode.PASSIVE
        manager.native = SimpleNamespace(foreground=lambda: int(menu.winId()))
        assert not manager.eligible()
        menu.hide()
        manager.target = None
