"""Deterministic, bounded, read-only filesystem inventory.

The scanner never writes source data. It rejects links/reparse points and security-limit
violations instead of returning a partial inventory. It revalidates paths immediately
before and after file opens and uses O_NOFOLLOW where the platform exposes it. This
narrows, but cannot eliminate, filesystem TOCTOU races.
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
_PATH_ERRORS = (OSError, RuntimeError, ValueError)


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
class _FileIdentity:
    size: int
    mtime_ns: int
    inode: int
    device: int


@dataclass(frozen=True)
class _Candidate:
    path: Path
    relative_path: str
    identity: _FileIdentity


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


def _identity(stat_result: os.stat_result | object) -> _FileIdentity:
    return _FileIdentity(
        size=int(getattr(stat_result, "st_size", 0)),
        mtime_ns=int(getattr(stat_result, "st_mtime_ns", 0)),
        inode=int(getattr(stat_result, "st_ino", 0)),
        device=int(getattr(stat_result, "st_dev", 0)),
    )


def _same_identity(first: os.stat_result | object, second: os.stat_result | object) -> bool:
    left = _identity(first)
    right = _identity(second)
    if left.size != right.size or left.mtime_ns != right.mtime_ns:
        return False
    if left.inode and right.inode and (left.inode != right.inode or left.device != right.device):
        return False
    return True


def _same_snapshot(snapshot: _FileIdentity, current: os.stat_result | object) -> bool:
    now = _identity(current)
    if snapshot.size != now.size or snapshot.mtime_ns != now.mtime_ns:
        return False
    if snapshot.inode and now.inode and (snapshot.inode != now.inode or snapshot.device != now.device):
        return False
    return True


def _resolve_existing_directory(path: Path, *, label: str) -> Path:
    try:
        raw_stat = os.lstat(path)
    except _PATH_ERRORS as exc:
        raise _fail(
            "FILESYSTEM_ERROR",
            f"{label} cannot be inspected.",
            "Check that the directory path is valid, exists, and is readable.",
        ) from exc

    if _is_link_or_reparse(raw_stat):
        raise _fail(
            "PATH_REJECTED",
            f"{label} must not be a symbolic link or reparse point.",
        )
    if not stat.S_ISDIR(raw_stat.st_mode):
        raise _fail("PATH_REJECTED", f"{label} must be a directory.")

    try:
        return path.resolve(strict=True)
    except _PATH_ERRORS as exc:
        raise _fail(
            "PATH_REJECTED",
            f"{label} cannot be resolved safely.",
        ) from exc


def _lexical_absolute(path: Path, *, label: str) -> Path:
    try:
        raw = os.fspath(path)
        if "\x00" in raw:
            raise ValueError("embedded NUL")
        return Path(os.path.abspath(raw))
    except _PATH_ERRORS as exc:
        raise _fail("PATH_REJECTED", f"{label} contains an invalid path.") from exc


def _resolve_scan_root_without_links(
    root: Path,
    *,
    allowed_input: Path,
    allowed_resolved: Path,
) -> Path:
    root_lexical = _lexical_absolute(root, label="Inventory root")
    allowed_lexical = _lexical_absolute(allowed_input, label="Allowed root")
    try:
        relative = root_lexical.relative_to(allowed_lexical)
    except ValueError as exc:
        raise _fail("PATH_REJECTED", "Inventory root is outside the allowed root.") from exc

    current = allowed_lexical
    for part in relative.parts:
        current = current / part
        try:
            component_stat = os.lstat(current)
        except _PATH_ERRORS as exc:
            raise _fail(
                "FILESYSTEM_ERROR",
                "An inventory-root path component cannot be inspected.",
            ) from exc
        if _is_link_or_reparse(component_stat):
            raise _fail(
                "PATH_REJECTED",
                "Inventory root must not traverse a symbolic link or reparse point.",
            )
        if not stat.S_ISDIR(component_stat.st_mode):
            raise _fail(
                "PATH_REJECTED",
                "Inventory root path contains a non-directory component.",
            )

    try:
        resolved = root_lexical.resolve(strict=True)
    except _PATH_ERRORS as exc:
        raise _fail("PATH_REJECTED", "Inventory root cannot be resolved safely.") from exc
    if not resolved.is_relative_to(allowed_resolved):
        raise _fail("PATH_REJECTED", "Inventory root escaped the allowed root.")
    return resolved


def _ensure_contained(path: Path, *, allowed_root: Path, expect_directory: bool) -> os.stat_result:
    try:
        raw_stat = os.lstat(path)
    except _PATH_ERRORS as exc:
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
    except _PATH_ERRORS as exc:
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


def _relative_path_text(path: Path, *, scan_root: Path) -> str:
    try:
        relative = path.relative_to(scan_root).as_posix()
        relative.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError) as exc:
        raise _fail(
            "PATH_REJECTED",
            "Inventory encountered a filename that cannot be represented safely as UTF-8.",
        ) from exc
    return relative


def _collect_candidates(
    scan_root: Path,
    *,
    allowed_root: Path,
    limits: Limits,
) -> tuple[list[_Candidate], int]:
    candidates: list[_Candidate] = []
    declared_total = 0
    visited_entries = 0
    stack: list[tuple[Path, int]] = [(scan_root, 0)]

    while stack:
        directory, directory_depth = stack.pop()
        _ensure_contained(directory, allowed_root=allowed_root, expect_directory=True)
        child_directories: list[tuple[Path, int]] = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    visited_entries += 1
                    if visited_entries > limits.max_entries:
                        raise _fail(
                            "LIMIT_EXCEEDED",
                            "Inventory visited-entry limit was exceeded.",
                        )

                    entry_depth = directory_depth + 1
                    if entry_depth > limits.max_depth:
                        raise _fail(
                            "LIMIT_EXCEEDED",
                            "Inventory directory depth limit was exceeded.",
                        )

                    path = Path(entry.path)
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except _PATH_ERRORS as exc:
                        raise _fail(
                            "FILESYSTEM_ERROR",
                            "A source entry cannot be inspected.",
                        ) from exc

                    if _is_link_or_reparse(entry_stat):
                        raise _fail(
                            "PATH_REJECTED",
                            "Inventory encountered a symbolic link or reparse point.",
                        )

                    relative_path = _relative_path_text(path, scan_root=scan_root)
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
                            identity=_identity(entry_stat),
                        )
                    )
        except _InventoryFailure:
            raise
        except _PATH_ERRORS as exc:
            raise _fail(
                "FILESYSTEM_ERROR",
                "A source directory cannot be read.",
            ) from exc

        child_directories.sort(key=lambda item: item[0].name, reverse=True)
        stack.extend(child_directories)

    candidates.sort(key=lambda item: item.relative_path)
    return candidates, declared_total


def _safe_fstat(descriptor: int) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except OSError as exc:
        raise _fail(
            "FILESYSTEM_ERROR",
            "A source file state cannot be inspected.",
        ) from exc


def _hash_candidate(
    candidate: _Candidate,
    *,
    allowed_root: Path,
    limits: Limits,
    total_remaining: int,
) -> InventoryFile:
    before = _ensure_contained(
        candidate.path,
        allowed_root=allowed_root,
        expect_directory=False,
    )
    if not _same_snapshot(candidate.identity, before):
        raise _fail(
            "SOURCE_CHANGED",
            "A source file changed after inventory enumeration.",
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
    read_limit = min(limits.file_bytes, total_remaining)
    primary_error: BaseException | None = None
    try:
        opened = _safe_fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_identity(before, opened):
            raise _fail(
                "SOURCE_CHANGED",
                "A source file changed during inventory.",
            )

        try:
            resolved_after_open = candidate.path.resolve(strict=True)
        except _PATH_ERRORS as exc:
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
            remaining = read_limit - bytes_read
            request_bytes = min(_CHUNK_BYTES, remaining + 1)
            if request_bytes <= 0:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory byte limit was exceeded while reading.",
                )
            try:
                chunk = os.read(descriptor, request_bytes)
            except OSError as exc:
                raise _fail(
                    "FILESYSTEM_ERROR",
                    "A source file cannot be read.",
                ) from exc
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > read_limit:
                raise _fail(
                    "LIMIT_EXCEEDED",
                    "Inventory byte limit was exceeded while reading.",
                )
            digest.update(chunk)

        finished = _safe_fstat(descriptor)
        if not _same_identity(opened, finished) or bytes_read != finished.st_size:
            raise _fail(
                "SOURCE_CHANGED",
                "A source file changed during inventory.",
            )

        path_after_read = _ensure_contained(
            candidate.path,
            allowed_root=allowed_root,
            expect_directory=False,
        )
        if not _same_identity(finished, path_after_read):
            raise _fail(
                "SOURCE_CHANGED",
                "A source path was replaced during inventory.",
            )
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if primary_error is None:
                raise _fail(
                    "FILESYSTEM_ERROR",
                    "A source file could not be closed cleanly.",
                ) from exc

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
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _fail(
            "PATH_REJECTED",
            "Inventory contains a path that cannot be encoded safely.",
        ) from exc
    return hashlib.sha256(canonical).hexdigest()


def scan_inventory(
    root: Path,
    *,
    limits: Limits,
    allowed_root: Path | None = None,
) -> InventoryResult:
    """Scan regular files without following links or writing to the source tree."""

    try:
        allowed_input = allowed_root if allowed_root is not None else root
        allowed = _resolve_existing_directory(allowed_input, label="Allowed root")
        if allowed_root is None:
            scan_root = allowed
        else:
            scan_root = _resolve_scan_root_without_links(
                root,
                allowed_input=allowed_input,
                allowed_resolved=allowed,
            )

        candidates, declared_total = _collect_candidates(
            scan_root,
            allowed_root=allowed,
            limits=limits,
        )
        files_list: list[InventoryFile] = []
        actual_total = 0
        for candidate in candidates:
            item = _hash_candidate(
                candidate,
                allowed_root=allowed,
                limits=limits,
                total_remaining=limits.total_bytes - actual_total,
            )
            files_list.append(item)
            actual_total += item.size

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

        files = tuple(files_list)
        inventory = Inventory(
            content_hash=_content_hash(files),
            total_bytes=actual_total,
            files=files,
        )
        return InventoryResult(inventory=inventory, diagnostics=())
    except _InventoryFailure as exc:
        return InventoryResult(inventory=None, diagnostics=(exc.diagnostic,))
