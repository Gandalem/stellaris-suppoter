from __future__ import annotations

import pytest

from stellaris_supporter.discovery.versioning import (
    build_dlc_evidence,
    resolve_version_evidence,
    tri_state_evidence,
)


def diagnostic_codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


def test_missing_version_remains_unknown_even_when_build_id_exists() -> None:
    result = resolve_version_evidence(metadata_build_id="123456")

    assert result.game_version is None
    assert result.game_version_source == "unknown"
    assert result.build_id == "123456"
    assert result.build_id_source == "metadata"
    assert "VERSION_UNKNOWN" in diagnostic_codes(result)


def test_user_reported_version_keeps_user_reported_provenance() -> None:
    result = resolve_version_evidence(
        user_reported_version="4.example",
        user_reported_branch="beta",
    )

    assert result.game_version == "4.example"
    assert result.game_version_source == "user_reported"
    assert result.branch == "beta"
    assert result.branch_source == "user_reported"


def test_metadata_version_wins_conflict_without_hiding_warning() -> None:
    result = resolve_version_evidence(
        metadata_version="metadata-version",
        user_reported_version="user-version",
    )

    assert result.game_version == "metadata-version"
    assert result.game_version_source == "metadata"
    assert "VERSION_EVIDENCE_CONFLICT" in diagnostic_codes(result)


def test_build_id_is_never_promoted_to_game_version() -> None:
    result = resolve_version_evidence(
        metadata_build_id="999999",
        metadata_branch="stable",
    )

    assert result.game_version is None
    assert result.build_id == "999999"
    assert result.branch == "stable"


def test_invalid_branch_remains_unknown_with_diagnostic() -> None:
    result = resolve_version_evidence(metadata_branch="experimental-custom")

    assert result.branch == "unknown"
    assert result.branch_source == "unknown"
    assert "BRANCH_UNKNOWN" in diagnostic_codes(result)


def test_branch_metadata_has_precedence_over_conflicting_user_report() -> None:
    result = resolve_version_evidence(
        metadata_branch="stable",
        user_reported_branch="beta",
    )

    assert result.branch == "stable"
    assert result.branch_source == "metadata"
    assert "BRANCH_EVIDENCE_CONFLICT" in diagnostic_codes(result)


def test_dlc_install_presence_does_not_imply_owned_or_enabled() -> None:
    result = build_dlc_evidence(
        "synthetic-dlc",
        installed=True,
        installed_source="filesystem",
        installed_evidence="synthetic/dlc/path",
    )

    assert result.installed.value is True
    assert result.installed.source == "filesystem"
    assert result.owned.value is None
    assert result.owned.source == "unknown"
    assert result.enabled.value is None
    assert result.enabled.source == "unknown"


def test_dlc_fields_keep_independent_values_and_sources() -> None:
    result = build_dlc_evidence(
        "synthetic-dlc",
        installed=True,
        installed_source="filesystem",
        owned=True,
        owned_source="user_reported",
        enabled=False,
        enabled_source="launcher",
    )

    assert result.installed.to_dict() == {
        "value": True,
        "source": "filesystem",
        "evidence": None,
    }
    assert result.owned.to_dict() == {
        "value": True,
        "source": "user_reported",
        "evidence": None,
    }
    assert result.enabled.to_dict() == {
        "value": False,
        "source": "launcher",
        "evidence": None,
    }


def test_dlc_inconsistent_signals_are_preserved_not_rewritten() -> None:
    result = build_dlc_evidence(
        "synthetic-dlc",
        installed=False,
        installed_source="filesystem",
        enabled=True,
        enabled_source="launcher",
    )

    assert result.installed.value is False
    assert result.enabled.value is True
    assert "DLC_STATE_INCONSISTENT" in diagnostic_codes(result)


def test_known_dlc_state_requires_non_unknown_source() -> None:
    with pytest.raises(ValueError, match="known DLC state"):
        tri_state_evidence(True)


def test_unknown_dlc_state_may_retain_checked_source_detail() -> None:
    evidence = tri_state_evidence(
        None,
        source="platform",
        evidence="platform lookup unavailable",
    )

    assert evidence.value is None
    assert evidence.source == "platform"
    assert evidence.evidence == "platform lookup unavailable"


def test_dlc_serialization_keeps_three_tri_state_fields() -> None:
    result = build_dlc_evidence(
        "synthetic-dlc",
        installed=True,
        installed_source="filesystem",
        owned=None,
        owned_source="platform",
        enabled=None,
        enabled_source="launcher",
    )
    payload = result.to_dict()

    assert payload["dlc_id"] == "synthetic-dlc"
    assert payload["installed"]["value"] is True
    assert payload["owned"]["value"] is None
    assert payload["enabled"]["value"] is None


def test_dlc_id_must_be_nonempty() -> None:
    with pytest.raises(ValueError, match="dlc_id"):
        build_dlc_evidence("   ")


def observations_by_key(result) -> dict[tuple[str, str], object]:
    return {(item.field, item.source): item for item in result.observations}


@pytest.mark.parametrize("reported", ["stable", "beta"])
def test_unrecognized_metadata_branch_blocks_user_fallback(reported: str) -> None:
    result = resolve_version_evidence(
        metadata_version="demo-version",
        metadata_branch="experimental-custom",
        user_reported_branch=reported,
    )
    by_key = observations_by_key(result)

    assert result.branch == "unknown"
    assert result.branch_source == "unknown"
    assert by_key[("branch", "metadata")].raw_value == "experimental-custom"
    assert by_key[("branch", "metadata")].normalized_value is None
    assert by_key[("branch", "metadata")].disposition == "unrecognized"
    assert by_key[("branch", "user_reported")].raw_value == reported
    assert by_key[("branch", "user_reported")].normalized_value == reported
    assert by_key[("branch", "user_reported")].disposition == "suppressed_by_metadata"
    assert "BRANCH_USER_FALLBACK_BLOCKED" in diagnostic_codes(result)


def test_version_conflict_preserves_both_raw_observations_in_serialization() -> None:
    result = resolve_version_evidence(
        metadata_version="demo-meta-v1",
        user_reported_version="demo-user-v2",
    )
    observations = result.to_dict()["observations"]

    assert {
        (item["field"], item["source"], item["raw_value"], item["disposition"])
        for item in observations
        if item["field"] == "game_version"
    } == {
        ("game_version", "metadata", "demo-meta-v1", "selected"),
        ("game_version", "user_reported", "demo-user-v2", "conflict"),
    }


def test_build_conflict_preserves_both_raw_observations_in_serialization() -> None:
    result = resolve_version_evidence(
        metadata_build_id="demo-meta-build",
        user_reported_build_id="demo-user-build",
    )
    observations = result.to_dict()["observations"]

    assert {
        (item["field"], item["source"], item["raw_value"], item["disposition"])
        for item in observations
        if item["field"] == "build_id"
    } == {
        ("build_id", "metadata", "demo-meta-build", "selected"),
        ("build_id", "user_reported", "demo-user-build", "conflict"),
    }


def test_unrecognized_branch_raw_label_survives_private_serialization() -> None:
    result = resolve_version_evidence(metadata_branch="demo-unknown-branch")
    branch_observation = observations_by_key(result)[("branch", "metadata")]

    assert result.branch == "unknown"
    assert branch_observation.raw_value == "demo-unknown-branch"
    assert branch_observation.normalized_value is None
    assert branch_observation.disposition == "unrecognized"
    assert result.to_dict()["observations"][0]["raw_value"] == "demo-unknown-branch"


def test_public_version_serialization_omits_raw_observations() -> None:
    result = resolve_version_evidence(
        metadata_version="demo-meta-v1",
        user_reported_version="demo-user-v2",
        metadata_branch="demo-unknown-branch",
        user_reported_branch="stable",
    )
    public_payload = result.to_public_dict()
    rendered = repr(public_payload)

    assert "observations" not in public_payload
    assert "demo-user-v2" not in rendered
    assert "demo-unknown-branch" not in rendered
