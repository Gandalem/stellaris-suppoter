"""Deterministic, bounded, read-only filesystem inventory.

The scanner never writes source data. It rejects links/reparse points and security-limit
violations instead of returning a partial inventory. It revalidates paths immediately
before file opens and uses O_NOFOLLOW where the platform exposes it. This narrows, but
cannot eliminate, filesystem TOCTOU races.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from stellaris_supporter.config import Limits
from stellaris_supporter.diagnostics import Diagnostic

_CHUNK_BYTES = 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class InventoryFile:
    relative_path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Inventory:
    content_hash: str
    total_bytes: int
    files: tuple[InventoryFile, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "content_hash": self.content_hash,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True)
class InventoryResult:
    inventory: Inventory | None
    diagnostics: tuple[Diagnostic, ...]

    @property
    def ok(self) -> bool:
        return self.inventory is not None and not any(
            item.severity == "error" for item in self.diagnostics
        )


@dataclass(frozen=True)
class _Candidate:
    path: Path
    relative_path: str
    size: int


class _InventoryFailure(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.code)
        self.diagnostic = diagnostic


def _fail(code: str, message: str, remediation: str | None = None) -> _InventoryFailure:
    return _InventoryFailure(Diagnostic(code, "error", message, remediation))


def _is_link_or_reparse(stat_result: os.stat_result | object) -> bool:
    mode = int(getattr(stat_result, "st_mode"))
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    return stat.S_ISLNK(mode) or bool(attributes & _REPARSE_POINT)


def _resolve_existing_directory(path: Path, *, label: str) -> Path:
    try:
        raw_stat = os.lstat(path)
    except OSError as exc:
        raise _fail(
            "FILESYSTEM_ERROR",
            f"{label} cannot be inspected.",
            "Check that the directory exists and is readable.",
        ) from exc

    if _is_link_or_reparse(raw_stat):
        raise _fail(
            "PATH_REJECTED",
            f"{label} must not be a symbolic link or reparse point.",
        )
    if not stat.S_ISDIR(raw_stat.st_mode):
        raise _fail("PATH_REJECTED", f"{label} must be a directory.")

    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail(
            "PATH_REJECTED",
            f"{label} cannot be resolved safely.",
        ) from exc
    return resolved


def _ensure_contained(path: Path, *, allowed_root: Path, expect_directory: bool) -> os.stat_result:
    try:
        raw_stat = os.lstat(path)
    except OSError as exc:
        raise _fail(
            "FILESYSTEM_ERROR",
            "A source path became unavailable during inventory.",
        ) from exc

    if _is_link_or_reparse(raw_stat):
        raise _fail(
            "PATH_REJECTED",
            "Inventory encountered a symbolic link or reparse point.",
        )

    expected = stat.S_ISDIR(raw_stat.st_mode) if expect_directory else stat.S_ISREG(raw_stat.st_mode)
    if not expected:
        raise _fail(
            "PATH_REJECTED",
            "Inventory encountered an unsupported filesystem object.",
        )

    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail(
            "PATH_REJECTED",
            "A source path cannot be resolved safely.",
        ) from exc
    if not resolved.is_relative_to(allowed_root):
        raise _fail(
            "PATH_REJECTED",
            "Inventory path escaped the allowed root.",
        )
    return raw_stat


def _collect_candidates(
    scan_root: Path,
    *,
    allowed_root: Path,
    limits: Limits,
) -> tuple[list[_Candidate], int]:
    candidates: list[_Candidate] = []
    declared_total = 0
    stack: list[tuple[Path, int]] = [(scan_root, 0)]

    while stack:
        directory, directory_depth = stack.pop()
        _ensure_contained(directory, allowed_root=allowed_root, expect_directory=True)
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(list(iterator), key=lambda entry: entry.name)
        except OSError as exc:
            raise _fail(
                "FILESYSTEM_ERROR",
                "A source directory cannot be read.",
            ) from exc

        child_directories: list[tuple[Path, int]] = []
        for entry in entries:
            entry_depth = directory_depth + 1
            if entry_depth > limits.max_depth:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory directory depth limit was exceeded.",
                )

            path = Path(entry.path)
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise _fail(
                    "FILESYSTEM_ERROR",
                    "A source entry cannot be inspected.",
                ) from exc

            if _is_link_or_reparse(entry_stat):
                raise _fail(
                    "PATH_REJECTED",
                    "Inventory encountered a symbolic link or reparse point.",
                )

            relative_path = path.relative_to(scan_root).as_posix()
            if stat.S_ISDIR(entry_stat.st_mode):
                child_directories.append((path, entry_depth))
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise _fail(
                    "PATH_REJECTED",
                    "Inventory encountered an unsupported filesystem object.",
                )

            if entry_stat.st_size > limits.file_bytes:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory file-size limit was exceeded.",
                )
            if len(candidates) + 1 > limits.max_files:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory file-count limit was exceeded.",
                )

            declared_total += entry_stat.st_size
            if declared_total > limits.total_bytes:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory total-byte limit was exceeded.",
                )
            candidates.append(
                _Candidate(
                    path=path,
                    relative_path=relative_path,
                    size=entry_stat.st_size,
                )
            )

        for child in reversed(child_directories):
            stack.append(child)

    candidates.sort(key=lambda item: item.relative_path)
    return candidates, declared_total


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    if first.st_size != second.st_size:
        return False
    first_inode = int(getattr(first, "st_ino", 0))
    second_inode = int(getattr(second, "st_ino", 0))
    first_device = int(getattr(first, "st_dev", 0))
    second_device = int(getattr(second, "st_dev", 0))
    if first_inode and second_inode and (first_inode != second_inode or first_device != second_device):
        return False
    return True


def _hash_candidate(
    candidate: _Candidate,
    *,
    allowed_root: Path,
    limits: Limits,
) -> InventoryFile:
    before = _ensure_contained(
        candidate.path,
        allowed_root=allowed_root,
        expect_directory=False,
    )
    if before.st_size != candidate.size:
        raise _fail(
            "SOURCE_CHANGED",
            "A source file changed during inventory.",
        )

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate.path, flags)
    except OSError as exc:
        raise _fail(
            "FILESYSTEM_ERROR",
            "A source file cannot be opened read-only.",
        ) from exc

    digest = hashlib.sha256()
    bytes_read = 0
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_identity(before, opened):
            raise _fail(
                "SOURCE_CHANGED",
                "A source file changed during inventory.",
            )

        try:
            resolved_after_open = candidate.path.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise _fail(
                "PATH_REJECTED",
                "A source file cannot be resolved safely after opening.",
            ) from exc
        if not resolved_after_open.is_relative_to(allowed_root):
            raise _fail(
                "PATH_REJECTED",
                "Inventory path escaped the allowed root.",
            )

        while True:
            try:
                chunk = os.read(descriptor, _CHUNK_BYTES)
            except OSError as exc:
                raise _fail(
                    "FILESYSTEM_ERROR",
                    "A source file cannot be read.",
                ) from exc
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > limits.file_bytes:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory file-size limit was exceeded while reading.",
                )
            digest.update(chunk)

        finished = os.fstat(descriptor)
        if not _same_identity(opened, finished) or bytes_read != finished.st_size:
            raise _fail(
                "SOURCE_CHANGED",
                "A source file changed during inventory.",
            )
    finally:
        os.close(descriptor)

    return InventoryFile(
        relative_path=candidate.relative_path,
        size=bytes_read,
        sha256=digest.hexdigest(),
    )


def _content_hash(files: tuple[InventoryFile, ...]) -> str:
    payload = [
        {"relative_path": item.relative_path, "sha256": item.sha256}
        for item in files
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def scan_inventory(
    root: Path,
    *,
    limits: Limits,
    allowed_root: Path | None = None,
) -> InventoryResult:
    """Scan regular files without following links or writing to the source tree."""

    try:
        allowed = _resolve_existing_directory(
            allowed_root if allowed_root is not None else root,
            label="Allowed root",
        )
        scan_root = _resolve_existing_directory(root, label="Inventory root")
        if not scan_root.is_relative_to(allowed):
            raise _fail(
                "PATH_REJECTED",
                "Inventory root is outside the allowed root.",
            )

        candidates, declared_total = _collect_candidates(
            scan_root,
            allowed_root=allowed,
            limits=limits,
        )
        files = tuple(
            _hash_candidate(candidate, allowed_root=allowed, limits=limits)
            for candidate in candidates
        )
        actual_total = sum(item.size for item in files)
        if actual_total != declared_total:
            raise _fail(
                "SOURCE_CHANGED",
                "Source sizes changed during inventory.",
            )
        if actual_total > limits.total_bytes:
            raise _fail(
                "LIMIT_EXCEEDED",
                "Inventory total-byte limit was exceeded.",
            )

        inventory = Inventory(
            content_hash=_content_hash(files),
            total_bytes=actual_total,
            files=files,
        )
        return InventoryResult(inventory=inventory, diagnostics=())
    except _InventoryFailure as exc:
        return InventoryResult(inventory=None, diagnostics=(exc.diagnostic,))
