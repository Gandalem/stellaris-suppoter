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
