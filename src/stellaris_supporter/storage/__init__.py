"""Public typed storage contracts and snapshot repository (TASK-010)."""

from stellaris_supporter.storage.identity import (
    MAX_FILES,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_BYTES,
    SCHEMA_VERSION,
    SnapshotError,
    SnapshotIdentity,
    SnapshotPolicy,
    SourceDescriptor,
    SourceFileInput,
    canonical_json,
    normalise_relative_path,
    snapshot_identity,
)
from stellaris_supporter.storage.repository import SnapshotRepository, SnapshotSummary

__all__ = [
    "MAX_FILES",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "SCHEMA_VERSION",
    "SnapshotError",
    "SnapshotIdentity",
    "SnapshotPolicy",
    "SnapshotRepository",
    "SnapshotSummary",
    "SourceDescriptor",
    "SourceFileInput",
    "canonical_json",
    "normalise_relative_path",
    "snapshot_identity",
]
