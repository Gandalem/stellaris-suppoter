"""Essential scope, provenance, snapshot and summary acceptance for card option 2."""

from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from stellaris_supporter.card_information import CardInformation, readable_detail
from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.config import Limits, Settings
from stellaris_supporter.desktop.settings import Card, Preferences
from stellaris_supporter.retrieval import SearchService
from stellaris_supporter.static_values import VERSION, numeric
from stellaris_supporter.storage import SnapshotError, SnapshotRepository


def fixture(tmp_path, cost="@price", local="", global_text="@price = 1250", extra=""):
    game = tmp_path / "game"
    tech = game / "common/technology/main.txt"
    tech.parent.mkdir(parents=True)
    tech.write_text(
        local
        + "\ntech_base={ cost=0 tier=0 area=physics }\n"
        + "tech_demo={ cost="
        + cost
        + " tier=1 area=physics category={ particles } "
        'prerequisites={ "tech_base" } is_rare=yes ' + extra + " }",
        encoding="utf-8",
    )
    variables = game / "common/scripted_variables/main.txt"
    variables.parent.mkdir(parents=True)
    variables.write_text(global_text, encoding="utf-8")
    for lang, title, base in (
        ("korean", "청색 레이저", "적색 레이저"),
        ("english", "Blue laser", "Red laser"),
    ):
        path = game / "localisation" / lang / "names.yml"
        path.parent.mkdir(parents=True)
        path.write_text(
            f'l_{lang}:\n tech_demo:0 "{title}"\n tech_base:0 "{base}"\n'
            ' tech_demo_desc:0 "A plain game description"\n particles:0 "입자"\n',
            encoding="utf-8-sig",
        )
    settings = Settings(
        tmp_path / "config.toml", game, tmp_path / "private", "korean", False, Limits()
    )
    repo = SnapshotRepository(settings.data_dir, game_root=game)
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    return settings, repo, sid, tech, variables


def answer(repo, sid, game_id="tech_demo", language="korean"):
    search = SearchService(repo)
    information = CardInformation(repo, search)
    try:
        return information.answer({"snapshot_id": sid, "game_id": game_id}, language)
    finally:
        information.close()
        search.close()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", "0"),
        ("1250", "1,250"),
        ("1234.500", "1,234.500"),
        ("1e3", None),
        ("-1", None),
        ("nan", None),
        ("@x", None),
        ("1+2", None),
        ("9" * 65, None),
    ],
)
def test_numeric_exact_and_bounded(text, expected):
    assert numeric(text) == expected


def test_display_uses_same_snapshot_proof_and_keeps_raw_answer(tmp_path):
    settings, repo, sid, _, _ = fixture(tmp_path)
    data = answer(repo, sid)
    view = data["card_view"]
    assert view["name"] == "청색 레이저"
    assert view["fields"]["cost"]["value"] == "1,250"
    assert view["fields"]["area"]["value"] == "물리학"
    assert view["fields"]["tier"]["value"] == "1단계"
    assert view["fields"]["description"]["value"] == "A plain game description"
    assert view["prerequisites"][0]["name"] == "적색 레이저"
    assert view["prerequisites_complete"]
    assert view["flags"] == ["희귀"]
    cost = next(f for f in data["results"][0]["facts"] if f["field_name"] == "cost")
    assert cost["raw_expression"] == "@price" and cost["support_status"] == "unsupported_expression"
    from stellaris_supporter.domain import SourceRef

    refs = view["fields"]["cost"]["sources"]
    assert [repo.citation_bytes(SourceRef(**r)).decode() for r in refs] == [
        "@price",
        "@price = 1250",
        "1250",
    ]
    assert {r["snapshot_id"] for r in refs} == {sid}
    zero = answer(repo, sid, "tech_base")["card_view"]
    assert zero["fields"]["cost"]["value"] == "0"
    assert zero["fields"]["tier"]["value"] == "0단계"
    assert zero["prerequisites_complete"] and not zero["prerequisites"]
    assert "최종 비용" not in readable_detail(view)
    assert answer(repo, sid, language="english")["card_view"]["name"] == "Blue laser"


@pytest.mark.parametrize(
    "local,global_text,cost,status",
    [
        ("@price=7", "", "@price", "resolved"),
        ("@price=7", "@price=7", "@price", "ambiguous"),
        ("", "@price=7\n@price=7", "@price", "ambiguous"),
        ("@price=7\n@price=7", "", "@price", "ambiguous"),
        ("", "@price=@other\n@other=7", "@price", "unsupported"),
        ("", "@price=-2", "@price", "unsupported"),
        ("", "@price=1e3", "@price", "unsupported"),
        ("", "@Price=7", "@price", "unresolved"),
        ("", "@price=7\nbroken={", "@price", "incomplete"),
        ("", "@price=7", "@price", "ambiguous"),
    ],
)
def test_scope_and_unsupported_cases(tmp_path, local, global_text, cost, status):
    extra = "cost=9" if status == "ambiguous" and not local and global_text == "@price=7" else ""
    _, repo, sid, _, _ = fixture(tmp_path, cost, local, global_text, extra)
    field = answer(repo, sid)["card_view"]["fields"]["cost"]
    assert field["status"] == status
    assert (field["value"] is not None) == (status == "resolved")


def test_variable_only_changes_missing_added_deleted_and_old_snapshot(tmp_path):
    settings, repo, old, _, variables = fixture(tmp_path, global_text="")
    assert answer(repo, old)["card_view"]["fields"]["cost"]["status"] == "unresolved"
    variables.write_text("@price=1250")
    added = index_technologies(repo, settings, allow_partial=True)
    assert added["snapshot_id"] != old
    sid = added["snapshot_id"]
    assert added["processing"]["reused_files"] >= 3
    assert answer(repo, sid)["card_view"]["fields"]["cost"]["value"] == "1,250"
    variables.write_text("@price=2500")
    latest = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    assert answer(repo, latest)["card_view"]["fields"]["cost"]["value"] == "2,500"
    assert answer(repo, sid)["card_view"]["fields"]["cost"]["value"] == "1,250"
    variables.unlink()
    removed = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    assert answer(repo, removed)["card_view"]["fields"]["cost"]["status"] == "unresolved"
    assert index_technologies(repo, settings, allow_partial=True)["reused"]
    assert answer(repo, old)["card_view"]["fields"]["cost"]["status"] == "unresolved"


def test_missing_new_manifest_is_error_legacy_manifest_does_not_read_live_files(tmp_path):
    _, repo, sid, _, variables = fixture(tmp_path)
    variables.write_text("@price=999999")
    with repo._connection() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (VERSION + ":" + sid,))
    with pytest.raises(SnapshotError, match="manifest") as error:
        answer(repo, sid)
    assert error.value.code == "CACHE_MISSING"
    # Synthetic old-policy snapshot: readers must not borrow current game files.
    with repo._connection() as conn:
        row = conn.execute(
            "SELECT policy_json FROM snapshots WHERE snapshot_id=?", (sid,)
        ).fetchone()
        policy = json.loads(row[0])
        policy["analysis_context"].pop("card_values")
        conn.execute(
            "UPDATE snapshots SET policy_json=? WHERE snapshot_id=?", (json.dumps(policy), sid)
        )
    assert answer(repo, sid)["card_view"]["fields"]["cost"]["status"] == "missing_data"


def test_summary_fields_and_identity_guards(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication, QScrollBar

    from stellaris_supporter.desktop.app import Manager
    from stellaris_supporter.desktop.technology_card import FieldsDialog, TechnologySummary

    app = QApplication.instance() or QApplication([])
    for path in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if __import__("pathlib").Path(path).is_file():
            QFontDatabase.addApplicationFont(path)
    _, repo, sid, _, _ = fixture(tmp_path)
    view = answer(repo, sid)["card_view"]
    view["prerequisites"] = [
        dict(view["prerequisites"][0], name="아주 긴 선행 기술 이름입니다 " * 6) for _ in range(8)
    ]
    widget = TechnologySummary()
    widget.set_data(view, ["area", "tier", "cost", "prerequisites", "description", "category"])
    widget.resize(340, 190)
    widget.show()
    app.processEvents()
    assert not widget.findChildren(QScrollBar)
    assert len(widget.visible_lines) <= 190 // widget.fontMetrics().lineSpacing()
    small = widget.rows(160, widget.fontMetrics().lineSpacing() * 4)
    assert any("추가" in line for line in small)
    assert "기본 게임 파일 기준" in small[-1]
    widget.set_data(view, ["area", "tier", "cost", "prerequisites"])
    folded = widget.rows(160, widget.fontMetrics().lineSpacing() * 4)
    assert "추가 2항목 · 상세 보기" in folded  # prerequisite details and rare badge
    view["flags"] = []
    assert "추가 1항목 · 상세 보기" in widget.rows(160, widget.fontMetrics().lineSpacing()*4)
    large = widget.rows(340, 600)
    assert "외 5개" in large
    dialog = FieldsDialog(["custom_old", "cost", "tier"])
    assert dialog.selected() == ["custom_old", "cost", "tier"]
    card = Card.create(kind="technology", game_id="tech_demo", snapshot_id=sid)
    state = SimpleNamespace(prefs=Preferences(cards=[card]))
    request = {
        **{k: asdict(card)[k] for k in ("uid", "snapshot_id", "game_id", "entity_key")},
        "language": "korean",
    }
    assert Manager.matches_card(state, card.uid, request)
    for key, changed in (
        ("snapshot_id", "b" * 64),
        ("entity_key", "c" * 64),
        ("language", "english"),
        ("uid", "a" * 32),
    ):
        assert not Manager.matches_card(state, card.uid, {**request, key: changed})
    state.prefs.cards.clear()
    assert not Manager.matches_card(state, card.uid, request)
    widget.close()
    dialog.close()


def test_preview_collision_preserves_card_and_late_response_is_discarded(tmp_path, monkeypatch):
    from dataclasses import replace

    from stellaris_supporter.desktop import app as desktop
    from stellaris_supporter.desktop.app import Manager, QMessageBox
    from stellaris_supporter.desktop.worker import Worker

    settings, repo, old, _, variables = fixture(tmp_path)
    variables.write_text("@price=2500")
    new = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    worker = Worker({})
    worker.configure(settings)
    target = worker.perform(
        "refs", {"game_id": "tech_demo", "kind": "technology", "snapshot_id": new}
    )["nodes"][0]
    original = Card.create(
        kind="technology",
        snapshot_id=old,
        game_id="tech_demo",
        rect=[42, 50, 300, 220],
        fields=["cost", "custom"],
    )
    collision = replace(original, uid="a" * 32, snapshot_id=new, entity_key=target["entity_key"])
    state = SimpleNamespace(
        prefs=Preferences(cards=[original, collision]),
        notifications=[],
        saved=[],
        requests=[],
        selected=[],
    )
    state.matches_card = lambda uid, request: Manager.matches_card(state, uid, request)
    state.notify = state.notifications.append
    state.manage_card = state.selected.append
    state.update_collision = lambda card: Manager.update_collision(state, card)

    def submit(kind, payload, callback, channel=None):
        state.requests.append(kind)
        callback(worker.perform(kind, payload))

    state.submit = submit
    state.save = lambda: state.saved.append(True) or True
    state.rebuild_cards = lambda: None
    state.refresh_card_data = lambda *args: None
    monkeypatch.setattr(desktop, "plain_question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    before = asdict(original)
    try:
        Manager.update_technology_card(state, original, new)
        assert asdict(original) == before
        assert state.selected == [collision.uid]
        assert "card_preview" not in state.requests and not state.saved
        old_data = worker.perform("card", {"card": asdict(original)})
        state.prefs.cards.remove(collision)
        Manager.update_technology_card(state, original, new)
        assert "card_preview" in state.requests and state.saved == [True]
        assert original.snapshot_id == new and original.entity_key == target["entity_key"]
        assert all(asdict(original)[k] == before[k] for k in ("uid", "rect", "fields"))
        applied = []
        state.card_list = SimpleNamespace(item=lambda row: SimpleNamespace(setText=lambda text: None))
        state.card_label = lambda card, data: Manager.card_label(state, card, data)
        state.cards = {original.uid: SimpleNamespace(card=original, set_data=applied.append)}
        Manager.show_card(state, original.uid, old_data)
        assert not applied
        current = worker.perform("card", {"card": asdict(original)})
        Manager.show_card(state, original.uid, current)
        assert applied == [current]
    finally:
        worker.stop()


def test_edit_actions_and_passive_input_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from stellaris_supporter.desktop.app import CardWindow
    from stellaris_supporter.desktop.model import Mode

    app = QApplication.instance() or QApplication([])
    calls = []
    native = SimpleNamespace(
        passive=lambda handle, value: calls.append(value),
        user=SimpleNamespace(SetWindowPos=lambda *a: None),
    )
    manager = SimpleNamespace(
        prefs=Preferences(),
        native=native,
        target=None,
        open_card_detail=lambda uid: None,
        manage_card=lambda uid: None,
        hide_overlay=lambda: None,
    )
    card = Card.create(kind="technology", snapshot_id="b" * 64, game_id="test")
    window = CardWindow(manager, card)
    target = SimpleNamespace(dpi=144, rect=(0, 0, 1920, 1080))
    window.present(Mode.INTERACTIVE, target)
    app.processEvents()
    assert window.actions.isVisible() and window.grip.isVisible()
    window.present(Mode.PASSIVE, target)
    assert not window.actions.isVisible()
    assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert calls == [False, True]
    window.present(Mode.HIDDEN, None)
    window.deleteLater()
    app.processEvents()


def test_variable_only_file_and_late_local_definition_are_snapshot_sources(tmp_path):
    settings, repo, _, tech, _ = fixture(tmp_path, global_text="")
    only = tech.with_name("only_variables.txt")
    only.write_text("@price=99")
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    assert any(source.relative_path.endswith("only_variables.txt") for source in repo.source_manifest(sid))
    assert answer(repo, sid)["card_view"]["fields"]["cost"]["status"] == "unresolved"
    # Other technology files are not a global variable namespace.
    tech.write_text(tech.read_text(encoding="utf-8")+"\n@price=77", encoding="utf-8")
    later = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    cost = answer(repo, later)["card_view"]["fields"]["cost"]
    assert cost["status"] == "unsupported" and cost["value"] is None
    assert "뒤에" in cost["reason"] and len(cost["sources"]) == 2


def test_truncated_facts_never_promote_a_first_cost(tmp_path):
    extra = " ".join(f"field_{i}=0" for i in range(70))+" cost=999"
    _, repo, sid, _, _ = fixture(tmp_path, extra=extra)
    data = answer(repo, sid)
    assert data["truncated"]
    assert data["card_view"]["fields"]["cost"]["value"] is None


def test_cost_proof_remains_reachable_when_raw_source_list_is_full():
    from stellaris_supporter.desktop.presentation import collect_sources
    base = {"snapshot_id": "a"*64, "relative_path": "common/technology/main.txt",
            "file_sha256": "b"*64, "byte_start": 0, "byte_end": 1}
    variable = {**base, "relative_path": "common/scripted_variables/main.txt"}
    data = {"raw_sources": [{**base, "byte_start": i, "byte_end": i+1} for i in range(160)],
            "card_view": {"definition_source_ref": base, "fields": {"cost": {"sources": [base, variable]}}}}
    sources = collect_sources(data)
    assert len(sources) == 128 and variable in sources and base in sources
