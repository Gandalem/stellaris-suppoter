"""Synthetic-only E-015/E-016/E-017 localisation regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import parse_bytes

CORPUS = Path(__file__).parent / "fixtures" / "synthetic" / "corpus"
ENGLISH = Path("localisation/english/demo_l_english.yml")
KOREAN = Path("localisation/korean/demo_l_korean.yml")
KOREAN_COLLISION = Path("localisation/korean/demo_l_korean_collision.yml")
TECHNOLOGY = Path("common/technology/00_demo_normal.txt")
SNAPSHOT = "synthetic-task-009"


def _context(source: bytes, relative: str, snapshot: str = SNAPSHOT) -> SourceContext:
    return SourceContext(
        snapshot_id=snapshot,
        source_kind="synthetic",
        source_id="project-fixture",
        relative_path=relative,
        file_sha256=hashlib.sha256(source).hexdigest(),
    )


def _doc(
    source: bytes,
    relative: str = "localisation/synthetic_l_english.yml",
    **limits: int,
):
    return parse_localisation(source, _context(source, relative), **limits)


def _catalog(*documents):
    return build_localisation_catalog(tuple(documents))


def _fixture(relative: Path):
    source = (CORPUS / relative).read_bytes()
    return _doc(source, relative.as_posix())


def test_e015_korean_english_and_id_fallback_and_provenance() -> None:
    catalog = _catalog(_fixture(KOREAN), _fixture(ENGLISH))
    ko = resolve_localisation(catalog, "demo_echo_theory", "korean")
    en = resolve_localisation(catalog, "demo_english_only", "korean")
    missing = resolve_localisation(catalog, "demo_missing_loc", "korean")

    assert ko.resolution == "resolved"
    assert ko.display_value == "메아리 직조"
    assert ko.language_used == "korean"
    assert ko.language_requested == "korean"
    assert ko.fallback == "none"
    assert ko.source_ref is not None
    assert ko.source_ref.relative_path == KOREAN.as_posix()
    assert en.display_value == "English Only Signal"
    assert en.language_used == "english"
    assert en.fallback == "english"
    assert en.source_ref is not None
    assert en.source_ref.relative_path == ENGLISH.as_posix()
    assert missing.resolution == "unresolved"
    assert missing.display_value == "demo_missing_loc"
    assert missing.fallback == "id"
    assert missing.language_used is None
    assert missing.source_ref is None
    assert [d.code for d in missing.diagnostics] == ["LOC_MISSING_TRANSLATION"]


def test_e015_other_requested_language_uses_english_with_provenance() -> None:
    catalog = _catalog(_fixture(KOREAN), _fixture(ENGLISH))
    german = resolve_localisation(catalog, "demo_echo_theory", "german")
    direct = resolve_localisation(catalog, "demo_echo_theory", "l_english")
    assert german.display_value == "Echo Weaving"
    assert german.language_used == "english"
    assert german.fallback == "english"
    assert direct.language_requested == "english"
    assert direct.fallback == "none"
    assert direct.language_used == "english"
    assert german.source_ref == direct.source_ref


def test_e015_language_specific_definitions_not_cross_contaminated() -> None:
    catalog = _catalog(_fixture(KOREAN), _fixture(ENGLISH))
    assert resolve_localisation(catalog, "demo_prism_lattice", "korean").display_value == (
        "프리즘 격자"
    )
    assert resolve_localisation(catalog, "demo_prism_lattice", "english").display_value == (
        "Prismatic Lattice"
    )
    assert resolve_localisation(catalog, "demo_korean_only", "english").resolution == (
        "unresolved"
    )


def test_e016_multistep_static_reference_expansion_with_provenance() -> None:
    doc = _doc(
        b'l_english:\n demo_a:0 "go $demo_b$"\n demo_b:0 "$demo_c$!"\n'
        b' demo_c:0 "finish"\n'
    )
    result = resolve_localisation(_catalog(doc), "demo_a", "english")
    assert result.display_value == "go finish!"
    assert result.resolution == "resolved"
    assert result.visits == 3
    assert [source.byte_start for source in result.reference_source_refs] == [
        doc.entries[1].source_ref.byte_start,
        doc.entries[2].source_ref.byte_start,
    ]
    assert result.source_ref == doc.entries[0].source_ref
    assert result.output_bytes == len(b"go finish!")
    assert result.scanned_bytes == sum(
        e.value_source_ref.byte_end - e.value_source_ref.byte_start for e in doc.entries
    )


@pytest.mark.parametrize(
    "source",
    [
        b'l_english:\n demo_a:0 "$demo_a$"\n',
        b'l_english:\n demo_a:0 "$demo_b$"\n demo_b:0 "$demo_a$"\n',
        b'l_english:\n demo_a:0 "$demo_b$"\n demo_b:0 "$demo_c$"\n demo_c:0 "$demo_a$"\n',
    ],
    ids=["self-cycle", "two-key-cycle", "three-key-cycle"],
)
def test_e016_cycle_is_partial_and_bounded(source: bytes) -> None:
    result = resolve_localisation(_catalog(_doc(source)), "demo_a", "english")
    assert result.resolution == "partial"
    assert not result.ok
    assert not result.complete
    assert not result.truncated
    assert "LOC_CYCLE" in [d.code for d in result.diagnostics]
    assert result.visits <= 3
    assert len(result.display_value) <= 32


def test_e016_existing_corpus_cycle() -> None:
    result = resolve_localisation(_catalog(_fixture(ENGLISH)), "demo_cycle_a", "korean")
    assert result.language_used == "english"
    assert result.fallback == "english"
    assert "LOC_CYCLE" in [d.code for d in result.diagnostics]


def test_e016_missing_reference_is_not_silently_resolved() -> None:
    result = resolve_localisation(
        _catalog(_doc(b'l_english:\n demo_a:0 "hello $demo_absent$"\n')),
        "demo_a",
    )
    assert result.display_value == "hello $demo_absent$"
    assert result.resolution == "partial"
    assert [d.code for d in result.diagnostics] == ["LOC_MISSING_REFERENCE"]


def test_e016_depth_and_visit_limits_stop_before_excessive_expansion() -> None:
    source = b"l_english:\n" + b"".join(
        f' demo_{i}:0 "$demo_{i + 1}$"\n'.encode()
        for i in range(12)
    ) + b' demo_12:0 "end"\n'
    doc = _doc(source)
    # Numeric suffix keys are valid when preceded by a letter and underscore.
    result = resolve_localisation(_catalog(doc), "demo_0", max_depth=4)
    assert result.truncated
    assert result.resolution == "partial"
    assert "LIMIT_EXCEEDED" in [d.code for d in result.diagnostics]
    assert result.visits == 4

    visit_limited = resolve_localisation(_catalog(doc), "demo_0", max_visits=3)
    assert visit_limited.truncated
    assert visit_limited.visits == 3


def test_e016_repeated_expansion_is_limited_by_visits_and_output() -> None:
    doc = _doc(
        b'l_english:\n demo_a:0 "$demo_b$$demo_b$$demo_b$$demo_b$"\n'
        b' demo_b:0 "abcdefgh"\n'
    )
    visit_limited = resolve_localisation(_catalog(doc), "demo_a", max_visits=2)
    assert visit_limited.truncated
    assert visit_limited.visits == 2
    assert "LIMIT_EXCEEDED" in [d.code for d in visit_limited.diagnostics]

    output_limited = resolve_localisation(_catalog(doc), "demo_a", max_output_bytes=15)
    assert output_limited.truncated
    assert output_limited.output_bytes <= 15
    assert output_limited.resolution == "partial"


def test_e016_scan_budget_bounds_revisiting_long_text() -> None:
    text = b"z" * 1024
    doc = _doc(
        b'l_english:\n demo_a:0 "$demo_b$$demo_b$"\n demo_b:0 "' + text + b'"\n'
    )
    result = resolve_localisation(_catalog(doc), "demo_a", max_scan_bytes=1100)
    assert result.scanned_bytes <= 1100
    assert result.truncated
    assert "LIMIT_EXCEEDED" in [d.code for d in result.diagnostics]


def test_e017_preserve_duplicates_in_one_file_and_across_files() -> None:
    english = _fixture(ENGLISH)
    korean = _fixture(KOREAN)
    collision = _fixture(KOREAN_COLLISION)
    assert [e.raw_value for e in english.entries if e.key == "demo_duplicate_loc"] == [
        "English First", "English Second"
    ]
    assert [e.occurrence for e in english.entries if e.key == "demo_duplicate_loc"] == [1, 2]
    catalog = _catalog(english, korean, collision)
    assert len(catalog.definitions("english", "demo_duplicate_loc")) == 2
    assert len(catalog.definitions("korean", "demo_prism_lattice")) == 2
    ambiguous_en = resolve_localisation(catalog, "demo_duplicate_loc", "english")
    ambiguous_ko = resolve_localisation(catalog, "demo_prism_lattice", "korean")
    assert ambiguous_en.resolution == ambiguous_ko.resolution == "ambiguous"
    assert ambiguous_ko.source_ref is None
    assert ambiguous_ko.language_used is None
    assert ambiguous_ko.display_value == "demo_prism_lattice"
    assert "LOC_DUPLICATE_KEY" in [d.code for d in ambiguous_en.diagnostics]


def test_e017_ambiguous_reference_does_not_choose_last_definition() -> None:
    doc = _doc(
        b'l_english:\n demo_root:0 "$demo_b$"\n'
        b' demo_b:0 "first"\n demo_b:0 "second"\n'
    )
    resolved = resolve_localisation(_catalog(doc), "demo_root")
    assert resolved.display_value == "$demo_b$"
    assert resolved.resolution == "partial"
    assert [d.code for d in resolved.diagnostics] == ["LOC_DUPLICATE_REFERENCE"]


def test_e017_dynamic_expressions_are_not_executed() -> None:
    result = resolve_localisation(_catalog(_fixture(ENGLISH)), "demo_dynamic")
    assert "[Root.GetName]" in result.display_value
    assert "Prismatic Lattice" in result.display_value
    assert result.resolution == "partial"
    assert "LOC_DYNAMIC_UNSUPPORTED" in [d.code for d in result.diagnostics]
    assert result.reference_source_refs


@pytest.mark.parametrize(
    "value",
    [b'"Text \xc2\xa3energy\xc2\xa3"', b'"Text \xc2\xa7Rred\xc2\xa7!"', b'"$Root.GetName|U$"'],
    ids=["icon", "colour", "dynamic-dollar"],
)
def test_e017_markups_are_preserved_and_marked_partial(value: bytes) -> None:
    doc = _doc(b"l_english:\n demo_dynamic:0 " + value + b"\n")
    result = resolve_localisation(_catalog(doc), "demo_dynamic")
    assert result.resolution == "partial"
    assert "LOC_DYNAMIC_UNSUPPORTED" in [d.code for d in result.diagnostics]


def test_e017_bom_crlf_unicode_byte_spans_and_comments() -> None:
    source = (
        b"\xef\xbb\xbf# origin: synthetic\r\n"
        b"l_korean: # header\r\n"
        + ' demo_hangul:19 "한글 \\"인용\\"과 \\\\ slash" # comment\r\n'.encode()
        + b' demo_final:0 "Last"'
    )
    doc = _doc(source)
    assert doc.ok
    assert len(doc.entries) == 2
    assert len(doc.comments) == 3
    first = doc.entries[0]
    assert first.marker == "19"
    assert first.source_ref.line_start == 3
    assert first.column_start == 2
    assert first.source_ref.raw_bytes(source).startswith(b"demo_hangul:19")
    assert first.value_source_ref.raw_bytes(source).decode() == first.raw_value
    assert first.quoted_value_source_ref.raw_bytes(source).startswith(b'"')
    assert first.display_value == '한글 "인용"과 \\ slash'
    assert first.value_column_start > first.column_start
    assert doc.headers[0].source_ref.line_start == 2
    assert doc.entries[1].source_ref.line_start == 4
    assert not source.endswith(b"\n")


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        (b'l_english:\n demo_a:0 "missing\n', "LOC_UNCLOSED_STRING"),
        (b'l_english\n demo_a:0 "value"\n', "LOC_INVALID_HEADER"),
        (b'l_english:\n demo_a:0 "ok" extra\n', "LOC_TRAILING_SYNTAX"),
        (b' demo_a:0 "before header"\n', "LOC_MISSING_HEADER"),
        (b'l_english:\n demo_a:0 noquotes\n', "LOC_UNSUPPORTED_SYNTAX"),
    ],
)
def test_e017_malformed_syntax_remains_unknown(source: bytes, expected_code: str) -> None:
    doc = _doc(source)
    assert not doc.ok
    assert not doc.complete
    assert expected_code in [d.code for d in doc.diagnostics]
    assert len(doc.unknown_spans) >= 1
    assert doc.raw_bytes(doc.unknown_spans[-1])


def test_e017_invalid_utf8_is_not_replaced_and_empty_is_distinct() -> None:
    bad = _doc(b'l_korean:\n demo:0 "bad\xff"\n')
    empty = _doc(b"")
    assert not bad.ok and not bad.complete
    assert bad.entries == ()
    assert bad.diagnostics[0].code == "ENCODING_ERROR"
    assert empty.ok and empty.complete and not empty.diagnostics
    catalog = _catalog(bad, empty)
    result = resolve_localisation(catalog, "demo_missing")
    assert result.resolution == "partial"
    assert "LOC_INCOMPLETE_SOURCE" in [d.code for d in result.diagnostics]


def test_e017_wrong_source_hash_is_rejected_before_spans() -> None:
    source = b'l_english:\n demo:0 "good"\n'
    context = _context(b"not the source", "localisation/bad.yml")
    doc = parse_localisation(source, context)
    assert doc.entries == ()
    assert not doc.complete
    assert doc.diagnostics[0].code == "LOC_SOURCE_MISMATCH"
    assert doc.diagnostics[0].source_ref is None


@pytest.mark.parametrize("relative", ["../unsafe.yml", "/root/file.yml", "C:\\local\\x.yml"])
def test_e017_unsafe_source_context_path_rejected(relative: str) -> None:
    source = b"l_english:\n"
    with pytest.raises(ValueError):
        parse_localisation(source, _context(source, relative))


def test_e017_source_snapshot_mismatch_is_not_combined() -> None:
    source = b'l_english:\n demo_a:0 "A"\n'
    first = parse_localisation(source, _context(source, "a.yml", "snapshot-a"))
    second = parse_localisation(source, _context(source, "b.yml", "snapshot-b"))
    catalog = _catalog(first, second)
    assert not catalog.complete
    assert catalog.entries == ()
    assert "LOC_SNAPSHOT_MISMATCH" in [d.code for d in catalog.diagnostics]


def test_e017_resource_limits_are_explicit_and_prevent_partial_success() -> None:
    source = b'l_english:\n demo_a:0 "a"\n demo_b:0 "b"\n'
    byte_limited = _doc(source, max_bytes=5)
    entry_limited = _doc(source, max_entries=1)
    line_limited = _doc(source, max_line_bytes=8)
    for doc in (byte_limited, entry_limited, line_limited):
        assert not doc.complete
        assert not doc.ok
        assert "LIMIT_EXCEEDED" in [d.code for d in doc.diagnostics]
    assert len(entry_limited.entries) == 1
    assert not line_limited.entries


def test_e017_bounded_diagnostics_for_many_malformed_rows() -> None:
    source = b"l_english:\n" + b"bad syntax\n" * 1000
    doc = _doc(source, max_diagnostics=5)
    assert len(doc.diagnostics) <= 5
    assert not doc.complete
    assert doc.diagnostics[-1].code == "LIMIT_EXCEEDED"


def test_e017_large_synthetic_reference_fanout_has_structural_limits() -> None:
    source = (
        b'l_english:\n demo_a:0 "' + b"$demo_b$" * 5000 + b'"\n'
        b' demo_b:0 "xyz"\n'
    )
    doc = _doc(source)
    assert doc.ok
    result = resolve_localisation(
        _catalog(doc), "demo_a", max_visits=100, max_output_bytes=1024
    )
    assert result.visits <= 100
    assert result.output_bytes <= 1024
    assert result.truncated
    assert "LIMIT_EXCEEDED" in [d.code for d in result.diagnostics]


def test_e017_large_input_is_rejected_before_utf8_decode() -> None:
    source = b"\xff" * 1024
    doc = _doc(source, max_bytes=128)
    assert [d.code for d in doc.diagnostics] == ["LIMIT_EXCEEDED"]
    assert doc.entries == ()


def test_e017_source_ranges_stay_small_relative_to_large_source() -> None:
    value = "가" * 20000
    source = ('l_korean:\n demo_large:0 "' + value + '"\n').encode()
    doc = _doc(source)
    assert doc.ok
    entry = doc.entries[0]
    assert entry.value_source_ref.byte_end - entry.value_source_ref.byte_start == len(
        value.encode()
    )
    assert entry._source is source
    assert entry.raw_value == value
    assert len(json.dumps(entry.to_dict())) < 1500


def test_technology_definition_and_localisation_provenance_remain_separate() -> None:
    raw_tech = (CORPUS / TECHNOLOGY).read_bytes()
    parsed = parse_bytes(raw_tech)
    assert parsed.ok
    adapted = adapt_technologies(
        parsed, raw_tech, _context(raw_tech, TECHNOLOGY.as_posix())
    )
    candidate = next(
        c for c in adapted.candidates if c.game_id == "demo_echo_theory"
    )
    original_ref = candidate.source_ref
    catalogue = _catalog(_fixture(KOREAN), _fixture(ENGLISH))
    linked = resolve_technology_name(candidate, catalogue, "korean")

    assert linked.technology_source_ref == original_ref
    assert linked.candidate is candidate
    assert linked.localisation.display_value == "메아리 직조"
    assert linked.localisation.source_ref is not None
    assert linked.localisation.source_ref.relative_path == KOREAN.as_posix()
    assert linked.technology_source_ref.relative_path == TECHNOLOGY.as_posix()
    assert linked.localisation.source_ref.file_sha256 != original_ref.file_sha256


def test_technology_cross_snapshot_link_is_refused() -> None:
    raw_tech = (CORPUS / TECHNOLOGY).read_bytes()
    candidate = adapt_technologies(
        parse_bytes(raw_tech),
        raw_tech,
        _context(raw_tech, TECHNOLOGY.as_posix(), "other-snapshot"),
    ).candidates[0]
    with pytest.raises(ValueError):
        resolve_technology_name(candidate, _catalog(_fixture(KOREAN)))


def test_reader_resolver_bad_limits_are_not_accepted() -> None:
    source = b'l_english:\n demo:0 "text"\n'
    with pytest.raises(ValueError):
        _doc(source, max_entries=0)
    with pytest.raises(ValueError):
        resolve_localisation(_catalog(_doc(source)), "demo", max_visits=0)
    with pytest.raises(ValueError):
        resolve_localisation(_catalog(_doc(source)), "demo", max_output_bytes=-1)
