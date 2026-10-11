"""PR #17 review R1-R4 follow-up; all inputs are project-authored synthetic bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from stellaris_supporter.domain import SourceContext
from stellaris_supporter.localisation import (
    MAX_LOCALISATION_LINE_BYTES,
    build_localisation_catalog,
    parse_localisation,
    resolve_localisation,
)
from stellaris_supporter.localisation.reader import _scan_entry_prefix


def _parse(source: bytes, **limits: int):
    context = SourceContext(
        snapshot_id="synthetic-pr17-review",
        source_kind="synthetic",
        source_id="review-regression",
        relative_path="localisation/english/demo_review.yml",
        file_sha256=hashlib.sha256(source).hexdigest(),
    )
    return parse_localisation(source, context, **limits)


def _resolve(value: str):
    source = (
        'l_english:\n demo_a:0 "' + value + '"\n'
        ' demo_b:0 "STATIC"\n'
    ).encode("utf-8")
    doc = _parse(source)
    assert doc.ok, doc.diagnostics
    return doc, resolve_localisation(
        build_localisation_catalog((doc,)), "demo_a", "english"
    )


class _CountingText(str):
    def __new__(cls, content: str):
        instance = super().__new__(cls, content)
        instance.lookups = 0
        return instance

    def __getitem__(self, index: int | slice) -> str:
        self.lookups += 1
        return super().__getitem__(index)


@pytest.mark.parametrize("n", [16_384, 32_768, 65_536, 131_072])
def test_r1_forward_scanner_near_linear_character_accesses(n: int) -> None:
    invalid = _CountingText("demo:" + " " * n)
    assert _scan_entry_prefix(invalid) is None
    assert invalid.lookups <= len(invalid) + 16


@pytest.mark.parametrize("n", [32_768, 65_536])
def test_r1_long_malformed_line_preserves_unknown_span(n: int) -> None:
    raw = b"demo:" + b" " * n
    source = b"l_english:\n" + raw + b"\r\n"
    doc = _parse(source)
    assert len(doc.headers) == 1
    assert not doc.ok and not doc.complete and not doc.entries
    assert [d.code for d in doc.diagnostics] == ["LOC_UNSUPPORTED_SYNTAX"]
    assert len(doc.unknown_spans) == 1
    span = doc.unknown_spans[0]
    assert span.line_start == 2
    assert span.byte_end - span.byte_start == len(raw)
    assert doc.raw_bytes(span) == raw


@pytest.mark.parametrize("marker", [None, "0", "0019"])
@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_r1_long_valid_marker_prefix_bom_crlf_and_multibyte(
    marker: str | None, newline: bytes,
) -> None:
    first = b"\xef\xbb\xbfl_korean:" + newline
    prefix = b" demo_value:" + (b"" if marker is None else marker.encode())
    value = ' "가# \\"인용\\" \\\\ slash"'.encode("utf-8")
    source = first + prefix + b" " * 65_536 + value + newline
    doc = _parse(source)
    assert doc.ok, doc.diagnostics
    entry = doc.entries[0]
    assert entry.marker == marker
    assert entry.language == "korean"
    assert entry.source_ref.line_start == 2
    assert entry.column_start == 2
    assert entry.raw_value == '가# \\"인용\\" \\\\ slash'
    assert entry.display_value == '가# "인용" \\ slash'
    assert entry.value_source_ref.raw_bytes(source) == entry.raw_value.encode()
    assert doc.raw_bytes(entry.source_ref).startswith(b"demo_value:")


def test_r1_line_budget_inclusive_and_above_one_mib() -> None:
    header = b"l_english:\n"
    near = b"demo:" + b" " * (MAX_LOCALISATION_LINE_BYTES - 5)
    assert len(near) == MAX_LOCALISATION_LINE_BYTES
    at = _parse(header + near)
    assert [d.code for d in at.diagnostics] == ["LOC_UNSUPPORTED_SYNTAX"]
    assert at.unknown_spans[0].byte_end - at.unknown_spans[0].byte_start == len(near)
    over = _parse(header + near + b" ")
    assert not over.complete and not over.entries
    assert [d.code for d in over.diagnostics] == ["LIMIT_EXCEEDED"]


@pytest.mark.parametrize(
    "value",
    [
        "[Root.$demo_b$]",
        "[Root.[Other.$demo_b$]]",
        "[Root.$demo_b$] [Other.$demo_b$]",
        "[Root.$demo_b$",
        "£energy$demo_b$£",
        "§R$demo_b$§!",
    ],
)
def test_r2_protected_dynamic_region_is_never_statically_expanded(value: str) -> None:
    doc, resolved = _resolve(value)
    assert resolved.display_value == value
    assert resolved.resolution == "partial"
    assert not resolved.reference_selections
    assert not resolved.reference_source_refs
    assert resolved.source_ref == doc.entries[0].source_ref
    count = 2 if value == "[Root.$demo_b$] [Other.$demo_b$]" else 1
    assert [d.code for d in resolved.diagnostics] == ["LOC_DYNAMIC_UNSUPPORTED"] * count


def test_r2_adjacent_outside_static_refs_still_expand() -> None:
    doc, resolved = _resolve("$demo_b$[Root.$demo_b$]$demo_b$")
    assert resolved.display_value == "STATIC[Root.$demo_b$]STATIC"
    assert resolved.resolution == "partial"
    assert [d.code for d in resolved.diagnostics] == ["LOC_DYNAMIC_UNSUPPORTED"]
    assert len(resolved.reference_selections) == 2
    assert all(s.language_used == "english" for s in resolved.reference_selections)
    assert all(s.source_ref == doc.entries[1].source_ref for s in resolved.reference_selections)


def test_r2_unsupported_backslash_dollar_never_expands() -> None:
    doc, resolved = _resolve(r"\$demo_b$")
    assert doc.entries[0].has_unsupported_escape
    assert doc.entries[0].raw_value == r"\$demo_b$"
    assert resolved.display_value == r"\$demo_b$"
    assert resolved.resolution == "partial"
    assert [d.code for d in resolved.diagnostics] == ["LOC_UNSUPPORTED_ESCAPE"]
    assert not resolved.reference_selections


def test_r2_escaped_reference_protection_does_not_swallow_next_reference() -> None:
    _, resolved = _resolve(r"\$demo_b$$demo_b$")
    assert resolved.display_value == r"\$demo_b$STATIC"
    assert resolved.resolution == "partial"
    assert len(resolved.reference_selections) == 1


def test_r2_supported_backslash_then_reference_resolves() -> None:
    doc, resolved = _resolve(r"\\$demo_b$")
    assert not doc.entries[0].has_unsupported_escape
    assert resolved.display_value == "\\STATIC"
    assert resolved.resolution == "resolved"
    assert len(resolved.reference_selections) == 1


def test_r2_supported_escaped_quote_then_reference_resolves() -> None:
    doc, resolved = _resolve(r'\"$demo_b$')
    assert not doc.entries[0].has_unsupported_escape
    assert resolved.display_value == '"STATIC'
    assert resolved.resolution == "resolved"


def test_r2_protected_self_reference_is_not_misdiagnosed_as_cycle() -> None:
    value = "[Root.$demo_a$]"
    _, resolved = _resolve(value)
    assert resolved.display_value == value
    assert [d.code for d in resolved.diagnostics] == ["LOC_DYNAMIC_UNSUPPORTED"]
    assert resolved.visits == 1


@pytest.mark.parametrize(
    ("source", "budget", "headers", "entries", "comments", "unknown"),
    [
        (b"l_english: # header", 1, 1, 0, 0, 0),
        (b'l_english:\n demo_key:0 "one" # inline', 2, 1, 1, 0, 0),
        (b"l_english:\n# first\n# second", 2, 1, 0, 1, 0),
        (b"l_english:\nnot a key", 1, 1, 0, 0, 0),
    ],
)
def test_r4_each_record_is_charged_before_append(
    source: bytes, budget: int, headers: int, entries: int, comments: int, unknown: int,
) -> None:
    doc = _parse(source, max_records=budget)
    assert not doc.complete
    assert (len(doc.headers), len(doc.entries), len(doc.comments), len(doc.unknown_spans)) == (
        headers, entries, comments, unknown,
    )
    assert sum((len(doc.headers), len(doc.entries), len(doc.comments), len(doc.unknown_spans))) <= budget
    assert doc.diagnostics[-1].code == "LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    ("source", "budget", "count"),
    [
        (b"l_english:", 1, 1),
        (b"l_english: # header", 2, 2),
        (b'l_english:\n demo_key:0 "one" # comment', 3, 3),
        (b"l_english:\n# first\n\n", 2, 2),
        (b"# standalone", 1, 1),
    ],
)
def test_r4_exact_budget_at_eof_is_success(source: bytes, budget: int, count: int) -> None:
    doc = _parse(source, max_records=budget)
    assert doc.ok and doc.complete and not doc.diagnostics
    assert len(doc.headers) + len(doc.entries) + len(doc.comments) == count


def test_r3_parsing_markdown_integrity_and_contract() -> None:
    content = (Path(__file__).resolve().parents[1] / "docs" / "PARSING.md").read_text(
        encoding="utf-8"
    )
    assert content.count("# 정적 파싱·현지화\n") == 1
    assert content.count("\n## 현지화\n") == 1
    assert chr(96) + "$KEY$" + chr(96) in content
    assert chr(96) + "$KEY# 정적 파싱·현지화" not in content
    assert "요청 언어 → 영어 → 원래 ID" in content
    assert "ambiguous" in content
    assert "LOC_DYNAMIC_UNSUPPORTED" in content
    assert "LIMIT_EXCEEDED" in content
    assert "8 MiB" in content
    assert "64" in content
