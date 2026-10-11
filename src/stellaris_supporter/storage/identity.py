"""Deterministic, safe snapshot identity independent of discovery order and clocks."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_FILES = 50_000
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
_ALLOWED_KINDS = frozenset({"synthetic", "base", "mod", "official", "wiki", "community"})
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class SnapshotError(ValueError):
    """Sanitised error for an invalid identity, source, or repository state."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _error(code: str, message: str) -> SnapshotError:
    return SnapshotError(code, message)


def normalise_relative_path(relative_path: str) -> str:
    """Canonical slash spelling, NFC-required, case preserved; never merge aliases.

    Both POSIX and Windows input separators are accepted. Case differences are
    *not* folded. Canonical Unicode NFC is required rather than silently
    merging different physical files on case-sensitive filesystems.
    """
    if not isinstance(relative_path, str) or not relative_path:
        raise _error("PATH_REJECTED", "Source relative path is missing.")
    if unicodedata.normalize("NFC", relative_path) != relative_path:
        raise _error("PATH_REJECTED", "Source path must be Unicode NFC.")
    text = relative_path.replace("\\", "/")
    if text.startswith("/") or "\x00" in text or ":" in text:
        raise _error("PATH_REJECTED", "Source path is not a safe relative path.")
    parts = text.split("/")
    if any(x in {"", ".", ".."} for x in parts):
        raise _error("PATH_REJECTED", "Source path contains unsafe components.")
    if len(text.encode("utf-8")) > 4096:
        raise _error("LIMIT_EXCEEDED", "Source path exceeds the byte budget.")
    for part in parts:
        if any(c in '<>"|?*' or ord(c) < 32 for c in part):
            raise _error("PATH_REJECTED", "Source path contains invalid characters.")
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in _WINDOWS_RESERVED:
            raise _error("PATH_REJECTED", "Source path contains reserved components.")
    return "/".join(parts)


def canonical_json(value: Any, *, max_bytes: int | None = None) -> bytes:
    """UTF-8, NFC input, sorted keys, no whitespace, NaN or platform objects."""
    def inspect(item: Any, depth: int = 0) -> None:
        if depth > 280:
            raise _error("LIMIT_EXCEEDED", "Canonical JSON nesting limit exceeded.")
        if item is None or isinstance(item, (str, bool, int)):
            if isinstance(item, str) and unicodedata.normalize("NFC", item) != item:
                raise _error("SCHEMA_ERROR", "Canonical JSON strings must be NFC.")
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                inspect(child, depth + 1)
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise _error("SCHEMA_ERROR", "Canonical JSON keys must be strings.")
                inspect(key, depth + 1)
                inspect(child, depth + 1)
            return
        raise _error("SCHEMA_ERROR", "Unsupported type in canonical JSON.")
    inspect(value)
    if max_bytes is None:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise _error("LIMIT_EXCEEDED", "JSON output byte budget must be positive.")
    # For large nested payloads do not allocate unbounded intermediate JSON.
    encoder = json.JSONEncoder(
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    chunks: list[bytes] = []
    total = 0
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        total += len(encoded)
        if total > max_bytes:
            raise _error("LIMIT_EXCEEDED", "Record JSON exceeds serialization budget.")
        chunks.append(encoded)
    return b"".join(chunks)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceFileInput:
    source_kind: str
    source_id: str
    relative_path: str
    data: bytes = field(repr=False, compare=False)
    expected_sha256: str | None = None
    live_path: Path | None = field(default=None, repr=False, compare=False)

    def descriptor(self) -> SourceDescriptor:
        if self.source_kind not in _ALLOWED_KINDS:
            raise _error("SCHEMA_ERROR", "Unknown source kind.")
        if (not isinstance(self.source_id, str) or not self.source_id
                or len(self.source_id.encode("utf-8")) > 256):
            raise _error("SCHEMA_ERROR", "Source ID must be non-empty and bounded.")
        if unicodedata.normalize("NFC", self.source_id) != self.source_id:
            raise _error("SCHEMA_ERROR", "Source ID must be Unicode NFC.")
        if not isinstance(self.data, bytes):
            raise _error("SCHEMA_ERROR", "Source must contain immutable bytes.")
        if len(self.data) > MAX_SOURCE_BYTES:
            raise _error("LIMIT_EXCEEDED", "Single source exceeds file byte limit.")
        path = normalise_relative_path(self.relative_path)
        digest = _digest(self.data)
        if self.expected_sha256 is not None and digest != self.expected_sha256:
            raise _error("SOURCE_CHANGED", "Source bytes differ from the inventory digest.")
        return SourceDescriptor(self.source_kind, self.source_id, path, digest, len(self.data))


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_kind: str
    source_id: str
    relative_path: str
    file_sha256: str
    size: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_kind, self.source_id, self.relative_path)

    def identity_fields(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "relative_path": self.relative_path,
            "file_sha256": self.file_sha256,
        }


@dataclass(frozen=True, slots=True)
class SnapshotPolicy:
    parser_version: str
    adapter_version: str
    policy_hash: str
    context_kind: str = "synthetic"
    analysis_context: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    game_version: str | None = None
    game_version_source: str = "unknown"
    build_id: str | None = None
    branch: str = "unknown"
    dlc_state: Mapping[str, Any] = field(default_factory=dict)
    mod_state: str = "unknown"

    def identity_fields(self) -> dict[str, Any]:
        if (isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int)
                or self.schema_version < 1 or self.schema_version > 1024):
            raise _error("SCHEMA_ERROR", "Snapshot schema identity version is invalid.")
        if self.context_kind not in {"synthetic", "base_install", "effective"}:
            raise _error("SCHEMA_ERROR", "Unknown snapshot analysis context.")
        if self.game_version_source not in {"metadata", "user_reported", "unknown"}:
            raise _error("SCHEMA_ERROR", "Unknown game version evidence source.")
        if self.branch not in {"stable", "beta", "unknown"}:
            raise _error("SCHEMA_ERROR", "Invalid version branch evidence.")
        if self.mod_state not in {"none_reported", "detected_unresolved", "resolved", "unknown"}:
            raise _error("SCHEMA_ERROR", "Invalid mod state.")
        for name in (self.parser_version, self.adapter_version):
            if not isinstance(name, str) or not name or len(name) > 128:
                raise _error("SCHEMA_ERROR", "Parser and adapter versions must be bounded.")
        if not isinstance(self.policy_hash, str) or _HEX64.fullmatch(self.policy_hash) is None:
            raise _error("SCHEMA_ERROR", "policy_hash must be lowercase SHA-256.")
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "adapter_version": self.adapter_version,
            "policy_hash": self.policy_hash,
            "context_kind": self.context_kind,
            "analysis_context": dict(self.analysis_context),
            "game_version": self.game_version,
            "game_version_source": self.game_version_source,
            "build_id": self.build_id,
            "branch": self.branch,
            "dlc_state": dict(self.dlc_state),
            "mod_state": self.mod_state,
        }


@dataclass(frozen=True, slots=True)
class SnapshotIdentity:
    snapshot_id: str
    content_hash: str
    sources: tuple[SourceDescriptor, ...]
    policy_json: str


def snapshot_identity(
    sources: tuple[SourceFileInput, ...], policy: SnapshotPolicy
) -> SnapshotIdentity:
    if len(sources) > MAX_FILES:
        raise _error("LIMIT_EXCEEDED", "Source count exceeds file budget.")
    descriptors = [item.descriptor() for item in sources]
    if sum(item.size for item in descriptors) > MAX_TOTAL_BYTES:
        raise _error("LIMIT_EXCEEDED", "Sources exceed aggregate byte budget.")
    descriptors.sort(key=lambda x: x.key)
    seen: set[tuple[str, str, str]] = set()
    folded: set[tuple[str, str, str]] = set()
    for descriptor in descriptors:
        if descriptor.key in seen:
            raise _error("COLLISION_UNRESOLVED", "Source identity is duplicated.")
        collision_key = (descriptor.source_kind, descriptor.source_id,
                         descriptor.relative_path.casefold())
        if collision_key in folded:
            # Never silently alias two case-sensitive paths on Windows.
            raise _error("PATH_REJECTED", "Source path has a case-insensitive collision.")
        seen.add(descriptor.key)
        folded.add(collision_key)
    content_hash = _digest(canonical_json([item.identity_fields() for item in descriptors]))
    policy_fields = policy.identity_fields()
    policy_json = canonical_json(policy_fields).decode("utf-8")
    snapshot_id = _digest(canonical_json({"content_hash": content_hash, **policy_fields}))
    return SnapshotIdentity(snapshot_id, content_hash, tuple(descriptors), policy_json)
