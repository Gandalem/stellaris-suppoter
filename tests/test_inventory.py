from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from stellaris_supporter.config import Limits
from stellaris_supporter.discovery.inventory import (
    _is_link_or_reparse,
    scan_inventory,
)


def limits(**overrides: int) -> Limits:
    values = {
        "file_bytes": 1024,
        "total_bytes": 4096,
        "max_depth": 8,
        "max_files": 20,
        "max_entries": 40,
        "query_chars": 512,
        "max_results": 100,
    }
    values.update(overrides)
    return Limits(**values)


def write_tree(root: Path) -> dict[str, bytes]:
    payloads = {
        "a.txt": b"alpha\n",
        "nested/b.bin": b"\x00beta\xff",
        "nested/deeper/c.txt": b"gamma\r\n",
    }
    for relative, payload in payloads.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return payloads


def codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


def test_inventory_is_deterministic_across_absolute_roots_and_read_only(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    expected = write_tree(left)
    write_tree(right)
    before = {relative: (left / relative).read_bytes() for relative in expected}

    first = scan_inventory(left, limits=limits())
    second = scan_inventory(right, limits=limits())

    assert first.ok and second.ok
    assert first.inventory is not None
    assert second.inventory is not None
    assert first.inventory.content_hash == second.inventory.content_hash
    assert [item.relative_path for item in first.inventory.files] == [
        "a.txt",
        "nested/b.bin",
        "nested/deeper/c.txt",
    ]
    assert [item.to_dict() for item in first.inventory.files] == [
        item.to_dict() for item in second.inventory.files
    ]
    assert first.inventory.total_bytes == sum(len(value) for value in expected.values())
    after = {relative: (left / relative).read_bytes() for relative in expected}
    assert after == before


def test_inventory_opens_source_files_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_bytes(b"one")
    original_open = os.open
    seen_flags: list[int] = []

    def guarded_open(path, flags, *args, **kwargs):
        seen_flags.append(flags)
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC
        assert flags & write_flags == 0
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("stellaris_supporter.discovery.inventory.os.open", guarded_open)
    result = scan_inventory(root, limits=limits())

    assert result.ok
    assert seen_flags


def test_inventory_rejects_scan_root_outside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    result = scan_inventory(
        allowed / ".." / "outside",
        allowed_root=allowed,
        limits=limits(),
    )

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "secret"


def test_inventory_rejects_root_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "file.txt").write_text("preserve", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this runner: {exc}")

    result = scan_inventory(link, limits=limits())

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)
    assert (target / "file.txt").read_text(encoding="utf-8") == "preserve"


def test_inventory_rejects_internal_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this runner: {exc}")

    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_reparse_attribute_is_treated_as_link_even_without_symlink_mode() -> None:
    fake = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )
    assert _is_link_or_reparse(fake)


@pytest.mark.parametrize(
    ("limit_overrides", "files"),
    [
        ({"file_bytes": 3}, {"big.txt": b"1234"}),
        ({"total_bytes": 5}, {"a.txt": b"123", "b.txt": b"456"}),
        ({"max_files": 1}, {"a.txt": b"a", "b.txt": b"b"}),
    ],
)
def test_inventory_rejects_size_total_and_count_limits(
    tmp_path: Path,
    limit_overrides: dict[str, int],
    files: dict[str, bytes],
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for relative, payload in files.items():
        (root / relative).write_bytes(payload)
    before = {relative: (root / relative).read_bytes() for relative in files}

    result = scan_inventory(root, limits=limits(**limit_overrides))

    assert result.inventory is None
    assert "LIMIT_EXCEEDED" in codes(result)
    assert {relative: (root / relative).read_bytes() for relative in files} == before


def test_inventory_rejects_depth_limit(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = root / "one" / "two" / "three.txt"
    target.parent.mkdir(parents=True)
    target.write_text("deep", encoding="utf-8")

    result = scan_inventory(root, limits=limits(max_depth=2))

    assert result.inventory is None
    assert "LIMIT_EXCEEDED" in codes(result)
    assert target.read_text(encoding="utf-8") == "deep"


def test_inventory_converts_open_permission_error_to_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("preserve", encoding="utf-8")

    def denied_open(*_args, **_kwargs):
        raise PermissionError("synthetic denial")

    monkeypatch.setattr("stellaris_supporter.discovery.inventory.os.open", denied_open)
    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "FILESYSTEM_ERROR" in codes(result)
    assert target.read_text(encoding="utf-8") == "preserve"


def test_empty_inventory_has_stable_content_hash(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()

    first = scan_inventory(left, limits=limits())
    second = scan_inventory(right, limits=limits())

    assert first.ok and second.ok
    assert first.inventory is not None
    assert second.inventory is not None
    assert first.inventory.content_hash == second.inventory.content_hash
    assert first.inventory.files == ()


def test_inventory_content_hash_includes_relative_path(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_bytes(b"same bytes")
    (right / "b.txt").write_bytes(b"same bytes")

    first = scan_inventory(left, limits=limits())
    second = scan_inventory(right, limits=limits())

    assert first.ok and second.ok
    assert first.inventory is not None
    assert second.inventory is not None
    assert first.inventory.content_hash != second.inventory.content_hash


def test_inventory_rejects_leaf_file_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    link = root / "linked.txt"
    try:
        link.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this runner: {exc}")

    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_inventory_converts_fstat_errors_to_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_on_call: int,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_bytes(b"one")
    real_fstat = os.fstat
    calls = 0

    def failing_fstat(descriptor: int):
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise OSError("synthetic fstat failure")
        return real_fstat(descriptor)

    monkeypatch.setattr("stellaris_supporter.discovery.inventory.os.fstat", failing_fstat)
    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "FILESYSTEM_ERROR" in codes(result)


def test_inventory_converts_close_error_without_masking_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_bytes(b"one")
    real_close = os.close

    def failing_close(descriptor: int) -> None:
        real_close(descriptor)
        raise OSError("synthetic close failure")

    monkeypatch.setattr("stellaris_supporter.discovery.inventory.os.close", failing_close)
    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "FILESYSTEM_ERROR" in codes(result)


def test_inventory_rejects_nul_root_as_structured_diagnostic() -> None:
    result = scan_inventory(Path("bad\x00root"), limits=limits())

    assert result.inventory is None
    assert {"FILESYSTEM_ERROR", "PATH_REJECTED"} & codes(result)


@pytest.mark.skipif(os.name != "posix", reason="surrogateescape filename is POSIX-specific")
def test_inventory_rejects_non_utf8_filename_as_structured_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    raw = os.fsencode(root) + b"/bad_\xff.txt"
    descriptor = os.open(raw, os.O_WRONLY | os.O_CREAT, 0o600)
    os.close(descriptor)

    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)


def test_file_count_limit_stops_directory_enumeration_early(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(2000):
        (root / f"{index:04d}.txt").write_bytes(b"x")

    real_scandir = os.scandir
    yielded = 0

    class CountingScandir:
        def __init__(self, path: Path) -> None:
            self._inner = real_scandir(path)
            self._iterator = None

        def __enter__(self):
            self._iterator = self._inner.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._inner.__exit__(exc_type, exc, tb)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal yielded
            assert self._iterator is not None
            item = next(self._iterator)
            yielded += 1
            return item

    monkeypatch.setattr(
        "stellaris_supporter.discovery.inventory.os.scandir",
        lambda path: CountingScandir(path),
    )
    result = scan_inventory(root, limits=limits(max_files=1, max_entries=10))

    assert result.inventory is None
    assert "LIMIT_EXCEEDED" in codes(result)
    assert yielded <= 2


def test_directory_visit_limit_bounds_empty_directory_fanout(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(2000):
        (root / f"dir-{index:04d}").mkdir()

    result = scan_inventory(root, limits=limits(max_entries=25, max_files=1))

    assert result.inventory is None
    assert "LIMIT_EXCEEDED" in codes(result)


def test_growth_during_read_is_bounded_by_remaining_total_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "grow.txt"
    target.write_bytes(b"1234")
    real_read = os.read
    read_sizes: list[int] = []
    grown = False

    def growing_read(descriptor: int, size: int) -> bytes:
        nonlocal grown
        read_sizes.append(size)
        if not grown:
            grown = True
            with target.open("ab") as handle:
                handle.write(b"x" * 10_000)
        return real_read(descriptor, size)

    monkeypatch.setattr("stellaris_supporter.discovery.inventory.os.read", growing_read)
    result = scan_inventory(root, limits=limits(file_bytes=20_000, total_bytes=4))

    assert result.inventory is None
    assert {"LIMIT_EXCEEDED", "SOURCE_CHANGED"} & codes(result)
    assert read_sizes
    assert max(read_sizes) <= 5


def test_same_size_change_after_enumeration_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.discovery.inventory as inventory_module

    root = tmp_path / "root"
    root.mkdir()
    target = root / "one.txt"
    target.write_bytes(b"AAAA")
    real_collect = inventory_module._collect_candidates

    def mutate_after_collect(*args, **kwargs):
        candidates, total = real_collect(*args, **kwargs)
        target.write_bytes(b"BBBB")
        stat_result = target.stat()
        os.utime(
            target,
            ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000),
        )
        return candidates, total

    monkeypatch.setattr(inventory_module, "_collect_candidates", mutate_after_collect)
    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "SOURCE_CHANGED" in codes(result)


def test_path_replacement_after_read_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.discovery.inventory as inventory_module

    root = tmp_path / "root"
    root.mkdir()
    target = root / "one.txt"
    target.write_bytes(b"old!")
    real_lstat = os.lstat
    real_read = os.read
    read_started = False

    def marked_read(descriptor: int, size: int) -> bytes:
        nonlocal read_started
        read_started = True
        return real_read(descriptor, size)

    def replaced_lstat(path):
        current = real_lstat(path)
        if read_started and Path(path) == target:
            return SimpleNamespace(
                st_mode=current.st_mode,
                st_size=current.st_size + 10,
                st_mtime_ns=current.st_mtime_ns + 1,
                st_ctime_ns=current.st_ctime_ns + 1,
                st_ino=getattr(current, "st_ino", 0) + 1,
                st_dev=getattr(current, "st_dev", 0),
                st_file_attributes=getattr(current, "st_file_attributes", 0),
            )
        return current

    monkeypatch.setattr(inventory_module.os, "read", marked_read)
    monkeypatch.setattr(inventory_module.os, "lstat", replaced_lstat)
    result = scan_inventory(root, limits=limits())

    assert result.inventory is None
    assert "SOURCE_CHANGED" in codes(result)


def test_scan_root_rejects_intermediate_symlink_inside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    real = allowed / "real"
    sub = real / "sub"
    sub.mkdir(parents=True)
    (sub / "one.txt").write_bytes(b"one")
    alias = allowed / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this runner: {exc}")

    result = scan_inventory(alias / "sub", allowed_root=allowed, limits=limits())

    assert result.inventory is None
    assert "PATH_REJECTED" in codes(result)
