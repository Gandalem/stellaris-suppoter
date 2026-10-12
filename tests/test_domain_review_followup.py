"""R1/R2 regression tests: exact source backing and complete parse provenance.

Tests are authored synthetic bytes only. They deliberately fail on reviewed
PR #28 head a4af5b4d before the implementation is repaired.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain.generic import adapt_domain, verify_domain_candidate
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import parse_bytes


def _context(source: bytes) -> SourceContext:
    return SourceContext(
        "A", "synthetic", "authored", "common/buildings/sample.txt",
        hashlib.sha256(source).hexdigest(),
    )


def _candidate(source: bytes):
    ctx = _context(source)
    result = adapt_domain(parse_bytes(source), source, ctx, "building")
    assert result.ok and result.complete and len(result.candidates) == 1
    return ctx, result.candidates[0]


def test_r1_field_raw_backing_replacement_rejected_not_just_structural_equality():
    raw = b"building_x = { cost = 100 }"
    other = b"building_x = { cost = 999 }"
    ctx, original = _candidate(raw)
    value = original.fields[0].value
    assert value is not None
    forged_field = replace(original.fields[0], value=replace(value, _source=other))
    forged = replace(original, fields=(forged_field,))

    assert value.source_ref.raw_bytes(raw) == b"100"
    assert forged.fields[0].source_ref == original.fields[0].source_ref
    assert forged.fields[0].raw_value == "999"
    assert original.fields[0].raw_value == "100"
    assert original == forged  # _source deliberately excluded from equality.
    assert verify_domain_candidate(original, raw, ctx)
    assert not verify_domain_candidate(forged, raw, ctx)


def test_r1_condition_raw_backing_replacement_rejected():
    raw = b"building_x = { potential = { flag = yes } }"
    other = raw.replace(b"yes", b"no!")
    ctx, original = _candidate(raw)
    condition = original.conditions[0]
    assert condition.value is not None
    forged_condition = replace(condition, value=replace(condition.value, _source=other))
    forged = replace(original, conditions=(forged_condition,))
    assert forged.conditions[0].raw_value == "{ flag = no! }"
    assert condition.raw_value == "{ flag = yes }"
    assert original == forged
    assert verify_domain_candidate(original, raw, ctx)
    assert not verify_domain_candidate(forged, raw, ctx)


def test_r1_nested_field_and_condition_raw_child_backing_rejected():
    raw = b"building_x = { potential = { flag = yes } }"
    other = raw.replace(b"yes", b"no!")
    ctx, original = _candidate(raw)
    field = original.fields[0]
    assert field.value is not None
    original_child = field.value.children[0]
    child = replace(original_child, _source=other)
    nested = replace(field.value, children=(child,))
    assert child.raw == "flag = no!"
    assert nested.raw == "{ flag = yes }"
    forged_field = replace(original, fields=(replace(field, value=nested),))
    forged_condition = replace(original, conditions=(replace(original.conditions[0], value=nested),))
    assert verify_domain_candidate(original, raw, ctx)
    assert not verify_domain_candidate(forged_field, raw, ctx)
    assert not verify_domain_candidate(forged_condition, raw, ctx)


def test_r1_valid_nested_and_duplicate_fields_definitions_still_verify():
    raw = (
        b"building_x = { cost = 100 cost = 200 potential = { flag = yes } }\n"
        b"building_x = { cost = 300 }"
    )
    ctx = _context(raw)
    result = adapt_domain(parse_bytes(raw), raw, ctx, "building")
    assert [c.definition_occurrence for c in result.candidates] == [1, 2]
    assert [f.occurrence for f in result.candidates[0].fields] == [1, 2, 1]
    assert all(c.resolution == "ambiguous" for c in result.candidates)
    assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)


def test_r2_empty_foreign_parse_result_cannot_hide_real_definition():
    raw = b"building_x = { cost = 100 }"
    ctx = _context(raw)
    with pytest.raises(ValueError, match="ParseResult|source|parse"):
        adapt_domain(parse_bytes(b""), raw, ctx, "building")


def test_r2_truncated_parse_document_with_full_tokens_is_rejected():
    raw = b"building_x = { cost = 100 }"
    ctx = _context(raw)
    parsed = parse_bytes(raw)
    foreign = replace(parsed, document=replace(parsed.document, items=()))
    with pytest.raises(ValueError, match="ParseResult|source|parse"):
        adapt_domain(foreign, raw, ctx, "building")


def test_r2_wrong_utf8_bytes_never_yield_empty_success():
    raw = b"\xff"
    ctx = _context(raw)
    with pytest.raises(ValueError, match="ParseResult|source|parse"):
        adapt_domain(parse_bytes(b""), raw, ctx, "building")
    canonical = adapt_domain(parse_bytes(raw), raw, ctx, "building")
    assert canonical.blocked
    assert not canonical.complete
    assert not canonical.candidates
    assert any(d.code == "ENCODING_ERROR" for d in canonical.diagnostics)


@pytest.mark.parametrize("where", ["token", "node"])
def test_r2_modified_line_column_source_span_is_rejected(where):
    raw = b"building_x = { cost = 100 }"
    ctx = _context(raw)
    parsed = parse_bytes(raw)
    if where == "token":
        first = parsed.tokens[0]
        tampered = replace(
            parsed, tokens=(replace(first, span=replace(first.span, column_start=42)), *parsed.tokens[1:])
        )
    else:
        first = parsed.document.items[0]
        node = replace(first, span=replace(first.span, line_start=42))
        tampered = replace(parsed, document=replace(parsed.document, items=(node,)))
    with pytest.raises(ValueError, match="ParseResult|source|parse"):
        adapt_domain(tampered, raw, ctx, "building")


def test_r2_valid_bom_crlf_unicode_and_partial_parse_diagnostics():
    raw = "\ufeffbuilding_x = {\r\n description = \"한국어\"\r\n potential = { flag = yes }\r\n }".encode()
    ctx, candidate = _candidate(raw)
    assert candidate.fields[0].raw_value == '"한국어"'
    assert candidate.source_ref.raw_bytes(raw).startswith(b"building_x")
    assert verify_domain_candidate(candidate, raw, ctx)

    partial_raw = b"building_x = { cost = 100 odd ^ = 2 }"
    partial = adapt_domain(parse_bytes(partial_raw), partial_raw, _context(partial_raw), "building")
    assert not partial.complete and not partial.blocked
    assert partial.candidates and partial.candidates[0].resolution == "partial"
    assert any(d.code == "PARSE_UNKNOWN_SYNTAX" for d in partial.diagnostics)


def test_r2_hard_parser_depth_and_lexer_token_limits_still_block():
    raw = b"building_x = { nested = { deep = { value = 1 } } }"
    ctx = _context(raw)
    for parsed in (parse_bytes(raw, max_depth=1), parse_bytes(raw, max_tokens=5)):
        result = adapt_domain(parsed, raw, ctx, "building")
        assert result.blocked and not result.complete and not result.candidates
        assert any(d.code in {"PARSE_DEPTH_LIMIT", "LIMIT_EXCEEDED"} for d in result.diagnostics)


def test_r2_full_parse_comparison_happens_once_per_adaptation():
    raw = b"building_x = { cost = 100 }\nbuilding_y = { cost = 200 }"
    ctx = _context(raw)
    parsed = parse_bytes(raw)
    with patch(
        "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
    ) as canonical_parse:
        result = adapt_domain(parsed, raw, ctx, "building")
    assert len(result.candidates) == 2 and result.complete
    assert canonical_parse.call_count == 1

    with patch(
        "stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes
    ) as canonical_parse:
        assert verify_domain_candidate(result.candidates[0], raw, ctx)
    assert canonical_parse.call_count == 1
