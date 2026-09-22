"""Version, branch, and DLC evidence contracts.

This module deliberately models evidence without guessing Stellaris semantics from a
build ID, directory presence, or one DLC signal. Real installation-specific evidence
collection is a separate concern.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from stellaris_supporter.diagnostics import Diagnostic

VersionSource = Literal["metadata", "user_reported", "unknown"]
Branch = Literal["stable", "beta", "unknown"]
DlcSource = Literal["filesystem", "platform", "launcher", "user_reported", "unknown"]

_VERSION_SOURCES = {"metadata", "user_reported", "unknown"}
_BRANCHES = {"stable", "beta"}
_DLC_SOURCES = {"filesystem", "platform", "launcher", "user_reported", "unknown"}


@dataclass(frozen=True)
class VersionEvidence:
    game_version: str | None
    game_version_source: VersionSource
    build_id: str | None
    build_id_source: VersionSource
    branch: Branch
    branch_source: VersionSource
    diagnostics: tuple[Diagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "game_version": self.game_version,
            "game_version_source": self.game_version_source,
            "build_id": self.build_id,
            "build_id_source": self.build_id_source,
            "branch": self.branch,
            "branch_source": self.branch_source,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True)
class TriStateEvidence:
    value: bool | None
    source: DlcSource
    evidence: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and not isinstance(self.value, bool):
            raise TypeError("tri-state value must be true, false, or null")
        if self.source not in _DLC_SOURCES:
            raise ValueError("unsupported DLC evidence source")
        if self.value is not None and self.source == "unknown":
            raise ValueError("known DLC state requires a non-unknown evidence source")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DlcEvidence:
    dlc_id: str
    installed: TriStateEvidence
    owned: TriStateEvidence
    enabled: TriStateEvidence
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.dlc_id, str) or not self.dlc_id.strip():
            raise ValueError("dlc_id must be a non-empty string")

    def to_dict(self) -> dict[str, object]:
        return {
            "dlc_id": self.dlc_id,
            "installed": self.installed.to_dict(),
            "owned": self.owned.to_dict(),
            "enabled": self.enabled.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("evidence text must be a string or null")
    cleaned = value.strip()
    return cleaned or None


def _pick_text(
    metadata_value: str | None,
    user_value: str | None,
    *,
    conflict_code: str,
    conflict_message: str,
    diagnostics: list[Diagnostic],
) -> tuple[str | None, VersionSource]:
    metadata = _clean_text(metadata_value)
    user = _clean_text(user_value)
    if metadata is not None:
        if user is not None and user != metadata:
            diagnostics.append(Diagnostic(conflict_code, "warning", conflict_message))
        return metadata, "metadata"
    if user is not None:
        return user, "user_reported"
    return None, "unknown"


def _branch_value(
    value: str | None,
    *,
    source: VersionSource,
    diagnostics: list[Diagnostic],
) -> Branch | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.lower()
    if normalized in _BRANCHES:
        return normalized  # type: ignore[return-value]
    diagnostics.append(
        Diagnostic(
            "BRANCH_UNKNOWN",
            "warning",
            f"{source} branch evidence is not a supported stable/beta label.",
        )
    )
    return None


def resolve_version_evidence(
    *,
    metadata_version: str | None = None,
    metadata_build_id: str | None = None,
    metadata_branch: str | None = None,
    user_reported_version: str | None = None,
    user_reported_build_id: str | None = None,
    user_reported_branch: str | None = None,
) -> VersionEvidence:
    """Resolve independent version/build/branch evidence without cross-field inference."""

    diagnostics: list[Diagnostic] = []
    game_version, game_version_source = _pick_text(
        metadata_version,
        user_reported_version,
        conflict_code="VERSION_EVIDENCE_CONFLICT",
        conflict_message="Metadata and user-reported version evidence disagree; metadata is retained.",
        diagnostics=diagnostics,
    )
    if game_version is None:
        diagnostics.append(
            Diagnostic(
                "VERSION_UNKNOWN",
                "warning",
                "Game version is unknown because no explicit version evidence was provided.",
            )
        )

    build_id, build_id_source = _pick_text(
        metadata_build_id,
        user_reported_build_id,
        conflict_code="BUILD_EVIDENCE_CONFLICT",
        conflict_message="Metadata and user-reported build evidence disagree; metadata is retained.",
        diagnostics=diagnostics,
    )

    metadata_branch_value = _branch_value(
        metadata_branch,
        source="metadata",
        diagnostics=diagnostics,
    )
    user_branch_value = _branch_value(
        user_reported_branch,
        source="user_reported",
        diagnostics=diagnostics,
    )
    if metadata_branch_value is not None:
        branch: Branch = metadata_branch_value
        branch_source: VersionSource = "metadata"
        if user_branch_value is not None and user_branch_value != metadata_branch_value:
            diagnostics.append(
                Diagnostic(
                    "BRANCH_EVIDENCE_CONFLICT",
                    "warning",
                    "Metadata and user-reported branch evidence disagree; metadata is retained.",
                )
            )
    elif user_branch_value is not None:
        branch = user_branch_value
        branch_source = "user_reported"
    else:
        branch = "unknown"
        branch_source = "unknown"

    return VersionEvidence(
        game_version=game_version,
        game_version_source=game_version_source,
        build_id=build_id,
        build_id_source=build_id_source,
        branch=branch,
        branch_source=branch_source,
        diagnostics=tuple(diagnostics),
    )


def tri_state_evidence(
    value: bool | None,
    *,
    source: DlcSource = "unknown",
    evidence: str | None = None,
) -> TriStateEvidence:
    if source not in _DLC_SOURCES:
        raise ValueError("unsupported DLC evidence source")
    return TriStateEvidence(
        value=value,
        source=source,
        evidence=_clean_text(evidence),
    )


def build_dlc_evidence(
    dlc_id: str,
    *,
    installed: bool | None = None,
    installed_source: DlcSource = "unknown",
    installed_evidence: str | None = None,
    owned: bool | None = None,
    owned_source: DlcSource = "unknown",
    owned_evidence: str | None = None,
    enabled: bool | None = None,
    enabled_source: DlcSource = "unknown",
    enabled_evidence: str | None = None,
) -> DlcEvidence:
    """Build three independent DLC evidence fields without inferring one from another."""

    installed_field = tri_state_evidence(
        installed,
        source=installed_source,
        evidence=installed_evidence,
    )
    owned_field = tri_state_evidence(
        owned,
        source=owned_source,
        evidence=owned_evidence,
    )
    enabled_field = tri_state_evidence(
        enabled,
        source=enabled_source,
        evidence=enabled_evidence,
    )
    diagnostics: list[Diagnostic] = []
    if enabled is True and installed is False:
        diagnostics.append(
            Diagnostic(
                "DLC_STATE_INCONSISTENT",
                "warning",
                "DLC evidence says enabled=true while installed=false; fields are preserved without inference.",
            )
        )
    return DlcEvidence(
        dlc_id=dlc_id.strip(),
        installed=installed_field,
        owned=owned_field,
        enabled=enabled_field,
        diagnostics=tuple(diagnostics),
    )
