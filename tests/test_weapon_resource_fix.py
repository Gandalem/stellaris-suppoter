"""Economic control scope and single mutation notice regressions."""

import pytest
from test_weapon_cards import desktop_fixture
from test_weapons import Services, fixture

from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.weapon_cards import (
    POLICY_NOTICE,
    field_lines,
    numeric_detail_lines,
    project,
    summary_text,
)


@pytest.mark.parametrize("control", ["mult=2", "multiplier=@unknown", "trigger={always=yes}"])
def test_control_is_not_resource_and_does_not_publish_fixed_amount(tmp_path, control):
    settings, repo, old, text, table = fixture(tmp_path)
    text.write_text(
        text.read_text(encoding="utf-8").replace(
            "cost={alloys=@alloys}", "cost={alloys=@alloys " + control + "}"
        ),
        encoding="utf-8",
    )
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        old_detail = services.weapons.detail(
            {"snapshot_id": old, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        detail = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        assert next(r for r in old_detail["resources"] if r["section"] == "cost")["value"] == "13"
        assert {r["resource_id"] for r in detail["resources"]} == {"alloys", "energy"}
        cost = next(r for r in detail["resources"] if r["section"] == "cost")
        upkeep = next(r for r in detail["resources"] if r["section"] == "upkeep")
        assert cost["value"] is None and cost["number"] is None and cost["status"] == "incomplete"
        assert control.split("=")[0] in detail["resource_scopes"]["cost"]
        assert upkeep["value"] == "0" and upkeep["status"] == "resolved"
        assert len(cost["sources"]) >= 2
        assert field_lines(project(detail), "cost") == ["제작 비용 · 동적 계산 필요"]
        assert detail["fields"]["damage"]["value"] == "8–21"
    finally:
        services.close()


def test_duplicate_cost_blocks_remain_candidates(tmp_path):
    settings, repo, _, text, _ = fixture(tmp_path)
    text.write_text(
        text.read_text(encoding="utf-8").replace(
            "upkeep={energy=0}", "cost={alloys=7} upkeep={energy=0}"
        ),
        encoding="utf-8",
    )
    sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
    services = Services(repo)
    try:
        detail = services.weapons.detail(
            {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}, "korean"
        )
        costs = [r for r in detail["resources"] if r["section"] == "cost"]
        assert len(costs) == 2 and all(
            r["status"] == "ambiguous" and r["value"] is None for r in costs
        )
        assert field_lines(project(detail), "cost") == ["제작 비용 · 중복 선언 확인 필요"]
    finally:
        services.close()


def test_mutation_notice_once_in_detail_card_and_preview(tmp_path, monkeypatch):
    with desktop_fixture(tmp_path, monkeypatch) as (
        manager,
        worker,
        _,
        (settings, repo, text, table),
        _,
        desktop,
    ):
        table.rename(table.with_name("mutation_weapon_components.csv"))
        text.write_text(
            text.read_text(encoding="utf-8").replace(
                "cost={alloys=@alloys}", "cost={alloys=@alloys mult=2}"
            ),
            encoding="utf-8",
        )
        sid = index_technologies(repo, settings, allow_partial=True)["snapshot_id"]
        detail = worker.perform(
            "weapon_detail", {"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"}
        )
        assert (
            detail["fields"]["range"]["status"] == "policy_required"
            and detail["fields"]["range"]["declared"] == "40"
        )
        assert "\n".join(numeric_detail_lines(detail)).count(POLICY_NOTICE) == 1
        view = project(detail)
        assert (
            summary_text(view, ["damage", "range", "accuracy", "tracking", "power", "cost"]).count(
                POLICY_NOTICE
            )
            == 1
        )
        manager.weapon_browser.open_weapon({"snapshot_id": sid, "game_id": "SMALL_BLUE_LASER"})
        browser = manager.weapon_browser
        assert browser.weapon_text.toPlainText().count(POLICY_NOTICE) == 1
        browser.pin_weapon()
        card = manager.prefs.cards[0]
        window = manager.cards[card.uid]
        assert window.summary.accessibleName().count(POLICY_NOTICE) == 1
        assert "\n".join(window.summary.rows(450, 280)).count(POLICY_NOTICE) == 1
        assert all(r["resource_id"] != "mult" for r in detail["resources"])
