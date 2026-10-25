"""Essential weapon option 2 scope, provenance, history and snapshot acceptance."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from stellaris_supporter.card_information import CardInformation
from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.config import Limits, Settings
from stellaris_supporter.domain import SourceRef
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository
from stellaris_supporter.weapon_data import VERSION, csv_product
from stellaris_supporter.weapons import WeaponService

HEADER = [
    "key",
    "cost",
    "power",
    "min_damage",
    "max_damage",
    "hull_damage",
    "shield_damage",
    "shield_penetration",
    "armor_damage",
    "armor_penetration",
    "min_windup",
    "max_windup",
    "cooldown",
    "range",
    "accuracy",
    "tracking",
    "size_damage_factor",
    "end",
]


def fixture(tmp_path, extra="", duplicate_csv=False):
    game = tmp_path / "game"
    for path in (
        "common/technology",
        "common/component_templates",
        "common/component_sets",
        "common/scripted_variables",
        "localisation/korean",
        "localisation/english",
    ):
        (game / path).mkdir(parents=True)
    (game / "common/technology/main.txt").write_text(
        'tech_base={ cost=0 area=physics tier=0 }\ntech_lasers_2={ cost=1250 area=physics tier=1 prerequisites={ "tech_base" } }'
    )
    (game / "common/scripted_variables/main.txt").write_text("@alloys=13\n@negative=-7")
    parts = []
    for size in ("small", "medium", "large"):
        key = size.upper() + "_BLUE_LASER"
        upgrade = 'upgrades_to="SMALL_UV_LASER"' if size == "small" else ""
        parts.append(
            f'weapon_component_template={{key="{key}" size={size} component_set="BLUE_LASER" damage={{min=99 max=999}} power=@negative prerequisites={{"tech_lasers_2"}} potential={{yes=yes}} {upgrade} resources={{cost={{alloys=@alloys}} upkeep={{energy=0}}}} {extra}}}'
        )
    parts.append(
        'weapon_component_template={key="SMALL_UV_LASER" size=small prerequisites={"tech_lasers_2"} }'
    )
    text = game / "common/component_templates/main.txt"
    text.write_text("\n".join(parts), encoding="utf-8")
    (game / "common/component_templates/000_documentation.txt").write_text(
        "# -X costs power, X gives power.\n"
    )
    (game / "common/component_sets/main.txt").write_text('component_set={key="BLUE_LASER"}')
    table = game / "common/component_templates/weapon_components.csv"
    with table.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(HEADER)
        for key in ("SMALL_BLUE_LASER", "MEDIUM_BLUE_LASER", "LARGE_BLUE_LASER", "SMALL_UV_LASER"):
            writer.writerow(
                [
                    key,
                    "999",
                    "-7",
                    "8",
                    "21",
                    "1.25",
                    "0.5",
                    "0",
                    "1.5",
                    "0",
                    "5",
                    "20",
                    "30",
                    "40",
                    "0.9",
                    "0.5",
                    "0",
                    "",
                ]
            )
            if duplicate_csv and key == "SMALL_BLUE_LASER":
                writer.writerow(
                    [
                        key,
                        "999",
                        "-7",
                        "8",
                        "21",
                        "1.25",
                        "0.5",
                        "0",
                        "1.5",
                        "0",
                        "5",
                        "20",
                        "30",
                        "40",
                        "0.9",
                        "0.5",
                        "0",
                        "",
                    ]
                )
    names = {
        "tech_base": "적색 레이저",
        "tech_lasers_2": "청색 레이저",
        "BLUE_LASER": "청색 레이저 계열",
        "SMALL_BLUE_LASER": "청색 레이저 소형",
        "MEDIUM_BLUE_LASER": "청색 레이저 중형",
        "LARGE_BLUE_LASER": "청색 레이저 대형",
        "SMALL_UV_LASER": "자외선 레이저",
        "alloys": "합금",
        "energy": "에너지",
    }
    for lang in ("korean", "english"):
        lines = ["l_" + lang + ":"] + [
            f' {key}:0 "{value if lang == "korean" else key}"' for key, value in names.items()
        ]
        (game / f"localisation/{lang}/names.yml").write_text("\n".join(lines), encoding="utf-8-sig")
    settings = Settings(
        tmp_path / "config.toml", game, tmp_path / "private", "korean", False, Limits()
    )
    repo = SnapshotRepository(settings.data_dir, game_root=game)
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    return settings, repo, sid, text, table


class Services:
    def __init__(self, repo):
        self.search = SearchService(repo)
        self.cards = CardInformation(repo, self.search)
        self.weapons = WeaponService(repo, self.cards)

    def close(self):
        self.weapons.close()
        self.cards.close()
        self.search.close()


def test_search_group_detail_values_and_verified_proofs(tmp_path):
    _, repo, sid, _, _ = fixture(tmp_path)
    services = Services(repo)
    try:
        result = services.weapons.search(
            {"snapshot_id": sid, "technology_id": "tech_lasers_2"}, "korean"
        )
        family = next(v for v in result["items"] if v["type"] == "family")
        assert family["count"] == 3 and family["name"] == "청색 레이저 계열"
        children = services.weapons.search(
            {"snapshot_id": sid, "group_id": "BLUE_LASER", "grouped": False}, "korean"
        )
        assert [v["size"] for v in children["items"]] == ["small", "medium", "large"]
        data = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        assert data["fields"]["damage"]["value"] == "8–21"
        assert data["fields"]["range"]["value"] == "40"
        assert data["fields"]["range"]["proof_labels"][0] == "range 값"
        assert data["fields"]["accuracy"]["value"] == "90.0%"
        assert data["fields"]["power"]["value"] == "7"
        assert data["fields"]["power"]["label"] == "소비 전력"
        assert data["resources"][0]["value"] == "13"
        assert data["resources"][1]["value"] == "0"
        assert {v["game_id"] for v in data["links"]} == {"tech_lasers_2", "SMALL_UV_LASER"}
        assert data["conditions"][0]["field"] == "potential"
        from stellaris_supporter.desktop.presentation import collect_sources

        for ref in collect_sources(data):
            assert repo.citation_bytes(SourceRef(**ref))
        # Old technology-only default contracts retain their shape/domain.
        tech = services.search.search(Query("레이저", snapshot_id=sid))
        assert all(v.kind == "technology" for v in tech.results)
        card = services.cards.answer({"snapshot_id": sid, "game_id": "tech_lasers_2"}, "korean")
        assert card["card_view"]["fields"]["cost"]["value"] == "1,250"
    finally:
        services.close()


def test_csv_quoted_multiline_bom_empty_cells_and_limits():
    raw = b'\xef\xbb\xbf# comment\r\nkey;power;note;end\r\nW;0;"a;z\nxx";\r\n;;;;\r\n'
    data = csv_product(raw)
    assert data["complete"] and len(data["rows"]) == 1
    assert data["rows"][0]["values"][2] == "a;z\nxx"
    start, end, _, _ = data["rows"][0]["cells"][2]
    assert raw[start:end] == b'"a;z\nxx"'
    with pytest.raises(SnapshotError):
        csv_product(b"key;power\nW;" + b"1" * 65538)
    assert not csv_product(b"key;power;power\nW;1;2")["complete"]
    assert not csv_product(b"key;power\nW;1;2")["complete"]


def test_duplicate_csv_not_guessed_and_source_proof_paging(tmp_path):
    _, repo, sid, _, _ = fixture(tmp_path, duplicate_csv=True)
    services = Services(repo)
    try:
        data = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        assert data["fields"]["range"]["status"] == "ambiguous"
        assert data["fields"]["range"]["value"] is None
        proof = services.weapons.detail(
            {
                "snapshot_id": sid,
                "game_id": "SMALL_BLUE_LASER",
                "section": "field",
                "field": "range",
                "limit": 1,
            },
            "korean",
        )
        assert len(proof["items"]) == 1 and proof["more"]
    finally:
        services.close()


def test_csv_change_and_deleted_rows_keep_old_snapshot(tmp_path):
    settings, repo, sid, _, table = fixture(tmp_path)
    text = table.read_text(encoding="utf-8-sig").replace(";8;21;", ";10;25;")
    table.write_text(text, encoding="utf-8-sig")
    newer = index_technologies(repo, settings, allow_partial=True)
    services = Services(repo)
    try:
        assert newer["snapshot_id"] != sid
        assert newer["processing"]["parsed_files"] == 1
        assert (
            services.weapons.detail({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean")[
                "fields"
            ]["damage"]["value"]
            == "8–21"
        )
        assert (
            services.weapons.detail(
                {"snapshot_id": newer["snapshot_id"], "game_id": "SMALL_BLUE_LASER"}, "korean"
            )["fields"]["damage"]["value"]
            == "10–25"
        )
        assert index_technologies(repo, settings, allow_partial=True)["reused"]
        assert (
            index_technologies(repo, settings, allow_partial=True, full=True)["snapshot_id"]
            == newer["snapshot_id"]
        )
    finally:
        services.close()


def test_dynamic_resources_do_not_hide_static_damage_and_zero_is_not_missing(tmp_path):
    _, repo, sid, _, _ = fixture(tmp_path, extra='resources={inline_script={script="x"}}')
    services = Services(repo)
    try:
        data = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        assert data["fields"]["damage"]["value"] == "8–21" and not data["resources_complete"]
        assert not data["resources"]
    finally:
        services.close()


def test_missing_manifest_and_changed_relation_are_not_normal_values(tmp_path):
    _, repo, sid, _, _ = fixture(tmp_path)
    with repo._connection() as conn:
        conn.execute(
            "UPDATE relations SET target_game_id='WRONG' WHERE snapshot_id=? AND relation_kind='weapon_upgrade'",
            (sid,),
        )
    services = Services(repo)
    try:
        with pytest.raises(SnapshotError):
            services.weapons.detail({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean")
    finally:
        services.close()
    with repo._connection() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (VERSION + ":" + sid,))
    services = Services(repo)
    try:
        with pytest.raises(SnapshotError):
            services.weapons.search({"snapshot_id": sid}, "korean")
    finally:
        services.close()


def test_unknown_csv_is_not_hashed_or_budgeted(tmp_path):
    settings, repo, _, _, table = fixture(tmp_path)
    unrelated = table.with_name("unrelated.csv")
    unrelated.write_bytes(b"x" * (settings.limits.file_bytes + 1))
    assert index_technologies(repo, settings, allow_partial=True)["reused"]


def test_weapon_qt_navigation_and_stale_response(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from stellaris_supporter.desktop import app as desktop
    from stellaris_supporter.desktop.settings import Preferences
    from stellaris_supporter.desktop.worker import Worker

    settings, repo, sid, _, _ = fixture(tmp_path)
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    for font in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(font).is_file():
            QFontDatabase.addApplicationFont(font)
    monkeypatch.setattr(desktop, "Windows", lambda: None)
    monkeypatch.setattr(desktop, "discover_installations", lambda: ())
    manager = desktop.Manager(
        Preferences(game_root=str(settings.game_root), data_dir=str(settings.data_dir)),
        tmp_path / "desktop.json",
    )
    manager.timer.stop()
    worker = Worker({})
    worker.configure(settings)
    manager.snapshot.blockSignals(True)
    manager.snapshot.addItem("new", sid)
    manager.snapshot.blockSignals(False)
    manager.active_snapshot = sid
    try:
        monkeypatch.setattr(
            manager,
            "submit",
            lambda kind, p, callback, channel=None: callback(worker.perform(kind, p)),
        )
        browser = manager.weapon_browser
        browser.search()
        assert browser.search_tree.topLevelItemCount() == 2
        group = next(
            browser.search_tree.topLevelItem(i)
            for i in range(2)
            if browser.search_tree.topLevelItem(i).data(0, 256).get("type") == "family"
        )
        browser.expand_group(group)
        assert group.childCount() == 3
        browser.choose_weapon(group.child(0))
        assert "8–21" in browser.weapon_text.toPlainText()
        assert browser.link_list.count() == 2
        technology = next(
            browser.link_list.item(i)
            for i in range(2)
            if browser.link_list.item(i).data(256)["kind"] == "technology"
        )
        browser.choose_link(technology)
        assert (
            browser.current["kind"] == "technology"
            and browser.related_tree.topLevelItemCount() == 2
        )
        assert "기본 연구 비용" in browser.tech_proof.toPlainText()
        assert "SHA256:" in browser.tech_technical.toPlainText()
        browser.tech_tabs.setCurrentIndex(1)
        browser.open_weapon({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"})
        browser.back()
        assert browser.current["kind"] == "technology" and browser.tech_tabs.currentIndex() == 1
        browser.back()
        assert browser.current["kind"] == "weapon"
        browser.back()
        assert browser.current["kind"] == "search" and browser.query.text() == ""
        selected_after_index = []
        monkeypatch.setattr(
            manager,
            "refresh_snapshots",
            lambda **kwargs: selected_after_index.append(kwargs.get("preferred_snapshot")),
        )
        manager.query_revision = manager.index_query_revision = 10
        manager.index_done({"snapshot_id": "b" * 64})
        assert selected_after_index[-1] == "b" * 64
        manager.query_revision = 11
        manager.index_done({"snapshot_id": "c" * 64})
        assert selected_after_index[-1] is None
        # Existing open details remain pinned, while the home query can select a newer snapshot.
        manager.show_snapshots(
            {
                "rows": [
                    {"snapshot_id": sid, "status": "partial"},
                    {"snapshot_id": "b" * 64, "status": "ready"},
                ],
                "active": "b" * 64,
                "truncated": False,
            },
            preferred_snapshot="b" * 64,
        )
        assert manager.sid() == "b" * 64 and browser.current["payload"]["snapshot_id"] == sid
        manager.active_snapshot = sid
        queued = []
        monkeypatch.setattr(
            manager,
            "submit",
            lambda kind, p, callback, channel=None: queued.append((kind, p, callback)),
        )
        browser.open_weapon({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"})
        callback = queued[-1][2]
        browser.open_weapon({"snapshot_id": sid, "game_id": "SMALL_UV_LASER"})
        callback(
            worker.perform("weapon_detail", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"})
        )
        assert (
            browser.current["payload"]["game_id"] == "SMALL_UV_LASER"
            and not browser.weapon_text.toPlainText()
        )
    finally:
        worker.stop()
        # Avoid application quit affecting other widget cases.
        manager.exiting = True
        manager.timer.stop()
        manager.hide()
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


@pytest.mark.parametrize(
    "raw,status,expected",
    [("", "missing", None), ("0", "resolved", "0"), ("1e3", "unsupported", None)],
)
def test_csv_empty_zero_and_expression_are_distinct(tmp_path, raw, status, expected):
    settings, repo, _, _, table = fixture(tmp_path)
    rows = list(csv.reader(table.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    rows[1][2] = raw
    with table.open("w", newline="", encoding="utf-8-sig") as stream:
        csv.writer(stream, delimiter=";").writerows(rows)
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        power = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )["fields"]["power"]
        assert power["status"] == status and power["value"] == expected
    finally:
        services.close()


def test_duplicate_definitions_and_cross_table_collision_require_selection(tmp_path):
    settings, repo, _, text, table = fixture(tmp_path)
    text.write_text(
        text.read_text(encoding="utf-8")
        + '\nweapon_component_template={key="SMALL_BLUE_LASER" size=small}',
        encoding="utf-8",
    )
    mutation = table.with_name("mutation_weapon_components.csv")
    mutation.write_bytes(table.read_bytes())
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        result = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        assert result["status"] == "ambiguous" and len(result["items"]) == 2
        assert len({v["entity_key"] for v in result["items"]}) == 2
        selected = services.weapons.detail(
            {"snapshot_id": sid, "entity_key": result["items"][0]["entity_key"]}, "korean"
        )
        assert selected["fields"]["range"]["status"] == "ambiguous"
    finally:
        services.close()


def test_mutation_table_values_are_declared_without_invented_merge(tmp_path):
    settings, repo, _, _, table = fixture(tmp_path)
    table.rename(table.with_name("mutation_weapon_components.csv"))
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        value = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )["fields"]["range"]
        assert (
            value["value"] is None
            and value["status"] == "policy_required"
            and value["declared"] == "40"
        )
    finally:
        services.close()


def test_groups_page_without_duplicate_or_lost_children(tmp_path):
    settings, repo, _, text, _ = fixture(tmp_path)
    with text.open("a", encoding="utf-8") as stream:
        for index in range(26):
            stream.write(
                f'\nweapon_component_template={{key="EXTRA_{index:02}" size=small component_set="BLUE_LASER" prerequisites={{"tech_lasers_2"}}}}'
            )
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        items = []
        offset = 0
        while True:
            page = services.weapons.search(
                {
                    "snapshot_id": sid,
                    "group_id": "BLUE_LASER",
                    "grouped": False,
                    "offset": offset,
                    "limit": 5,
                },
                "korean",
            )
            items.extend(page["items"])
            offset += len(page["items"])
            if not page["truncated"]:
                break
        assert len(items) == 29 and len({v["entity_key"] for v in items}) == 29
    finally:
        services.close()


def test_missing_key_dependency_added_and_literal_signed_txt_value(tmp_path):
    settings, repo, old, text, _ = fixture(tmp_path)
    with text.open("a", encoding="utf-8") as stream:
        stream.write(
            '\nweapon_component_template={key="TXT_WEAPON" size=small power=@negative damage=0 prerequisites={"tech_new"}}'
        )
    missing = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    tech = settings.game_root / "common/technology/new.txt"
    tech.write_text("tech_new={cost=0 tier=0 area=physics}")
    new = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        before = services.weapons.detail(
            {"snapshot_id": missing, "game_id": "TXT_WEAPON"}, "korean"
        )
        assert before["fields"]["damage"]["value"] == "0"
        assert before["fields"]["power"]["value"] == "7"
        assert before["links"][0]["status"] == "unresolved"
        after = services.weapons.detail({"snapshot_id": new, "game_id": "TXT_WEAPON"}, "korean")
        assert after["links"][0]["status"] == "resolved"
        assert (
            services.weapons.detail({"snapshot_id": old, "game_id": "TXT_WEAPON"}, "korean")[
                "status"
            ]
            == "not_found"
        )
    finally:
        services.close()


def test_extra_unknown_entity_kind_fails_closed(tmp_path):
    _, repo, sid, _, _ = fixture(tmp_path)
    with repo._connection() as conn:
        conn.execute(
            "INSERT INTO entities SELECT snapshot_id,?,game_id,?,occurrence,source_kind,source_id,relative_path,byte_start,byte_end,resolution,candidate_json,localisation_json FROM entities WHERE snapshot_id=? AND kind='technology' LIMIT 1",
            ("f" * 64, "building", sid),
        )
    services = Services(repo)
    try:
        with pytest.raises(SnapshotError):
            services.weapons.search({"snapshot_id": sid}, "korean")
    finally:
        services.close()


def test_csv_size_scaled_damage_marks_special_with_source(tmp_path):
    settings, repo, _, _, table = fixture(tmp_path)
    rows = list(csv.reader(table.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    rows[1][16] = "0.5"
    with table.open("w", newline="", encoding="utf-8-sig") as stream:
        csv.writer(stream, delimiter=";").writerows(rows)
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        result = services.weapons.search(
            {"snapshot_id": sid, "text": "SMALL_BLUE_LASER", "grouped": False}, "korean"
        )
        item = result["items"][0]
        assert item["special"] and item["special_sources"]
        assert repo.citation_bytes(SourceRef(**item["special_sources"][0])) == b"0.5"
    finally:
        services.close()
