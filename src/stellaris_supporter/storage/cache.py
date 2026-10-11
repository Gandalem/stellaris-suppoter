"""Private content-addressed source bytes cache; never writes to game_root."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from stellaris_supporter.storage.identity import MAX_SOURCE_BYTES, SnapshotError

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_CHUNK = 1024 * 1024


def _is_unsafe_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _ensure_directory(path: Path) -> None:
    """Make explicit data/cache dirs only, verifying each existing ancestor."""
    path = Path(os.path.abspath(path))
    for component in (list(reversed(path.parents)) + [path]):
        if component.exists() or component.is_symlink():
            if _is_unsafe_link(component) or not component.is_dir():
                raise SnapshotError("PATH_REJECTED", "A data directory is unsafe.")
        else:
            try:
                component.mkdir()
            except FileExistsError:
                if _is_unsafe_link(component) or not component.is_dir():
                    raise SnapshotError("PATH_REJECTED", "A data directory is unsafe.") from None
            except OSError as exc:
                raise SnapshotError("CACHE_ERROR", "Could not create a private data directory.") from exc


def _read_verified_file(path: Path, *, expected_hash: str, expected_size: int) -> bytes:
    try:
        if _is_unsafe_link(path) or not path.is_file():
            raise SnapshotError("PATH_REJECTED", "Source or cache is a link/non-file.")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_size != expected_size:
                raise SnapshotError("SOURCE_CHANGED", "Source is not a regular file of expected size.")
            with os.fdopen(descriptor, "rb") as reader:
                descriptor = -1
                chunks: list[bytes] = []
                remaining = expected_size
                sha = hashlib.sha256()
                while True:
                    part = reader.read(min(_CHUNK, remaining + 1))
                    if not part:
                        break
                    if len(part) > remaining:
                        raise SnapshotError("SOURCE_CHANGED", "Source byte length changed.")
                    sha.update(part)
                    chunks.append(part)
                    remaining -= len(part)
                if remaining or sha.hexdigest() != expected_hash:
                    raise SnapshotError("SOURCE_CHANGED", "Source bytes differ from SHA-256.")
                return b"".join(chunks)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except SnapshotError:
        raise
    except (OSError, ValueError) as exc:
        raise SnapshotError("CACHE_ERROR", "Could not read source/cache bytes.") from exc


class BlobCache:
    """Shared by SHA, not by SourceRef; per-file metadata remains in SQLite."""

    def __init__(self, private_dir: Path) -> None:
        self.root = private_dir / "blobs"
        _ensure_directory(self.root)

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise SnapshotError("SOURCE_CHANGED", "Invalid content hash.")
        return self.root / digest[:2] / digest

    def read(self, digest: str, size: int) -> bytes:
        if size < 0 or size > MAX_SOURCE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Source byte size is out of bounds.")
        path = self._path(digest)
        if not path.parent.is_dir():
            raise SnapshotError("CACHE_MISSING", "Required source cache blob is missing.")
        if _is_unsafe_link(self.root) or _is_unsafe_link(path.parent):
            raise SnapshotError("PATH_REJECTED", "Cache directory is unsafe.")
        return _read_verified_file(path, expected_hash=digest, expected_size=size)

    def verify(self, digest: str, size: int) -> None:
        self.read(digest, size)

    def put(self, data: bytes, digest: str) -> None:
        if not isinstance(data, bytes) or len(data) > MAX_SOURCE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Cache source exceeds byte budget.")
        if hashlib.sha256(data).hexdigest() != digest:
            raise SnapshotError("SOURCE_CHANGED", "Source bytes do not match its hash.")
        path = self._path(digest)
        _ensure_directory(path.parent)
        if path.exists() or path.is_symlink():
            self.verify(digest, len(data))
            return
        temporary: str | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
            with os.fdopen(descriptor, "wb") as writer:
                writer.write(data)
                writer.flush()
                os.fsync(writer.fileno())
            self._verify_temporary(Path(temporary), digest, len(data))
            # Replacement affects only a data_dir child; it never follows a
            # destination symlink. No snapshot is activated before rechecking.
            if path.exists() or path.is_symlink():
                self.verify(digest, len(data))
            else:
                os.replace(temporary, path)
                temporary = None
                self.verify(digest, len(data))
                if os.name == "posix":
                    # Ensure the published directory entry survives process
                    # termination/power failure where the filesystem supports
                    # directory fsync. Windows uses atomic same-dir replacement.
                    dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    directory_fd = os.open(path.parent, dir_flags)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
        except SnapshotError:
            raise
        except OSError as exc:
            raise SnapshotError("CACHE_ERROR", "Cannot persist a source blob.") from exc
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _verify_temporary(path: Path, digest: str, size: int) -> None:
        _read_verified_file(path, expected_hash=digest, expected_size=size)


def verify_live_source(path: Path, root: Path, expected_hash: str, size: int) -> None:
    """Recheck an explicitly allowed game-root file without ever writing to it."""
    target = Path(os.path.abspath(path))
    root = Path(os.path.abspath(root))
    if target == root or not target.is_relative_to(root):
        raise SnapshotError("PATH_REJECTED", "Live source is outside the allowed root.")
    if any(_is_unsafe_link(p) for p in [root, *list(target.parents)[:len(target.parts)-len(root.parts)], target]):
        raise SnapshotError("PATH_REJECTED", "Live source path contains a link.")
    _read_verified_file(target, expected_hash=expected_hash, expected_size=size)
