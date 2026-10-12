"""PR #29 R1/P2: bound diagnostics inside synthetic government wrappers.

These authored synthetic regressions are committed and run *before* the fix so
that the failing 1,200-definition/unsupported-child cases can be measured.
"""

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain import generic as domain
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS


def _fixture(children: str):
    source = f"governments = {{ {children} }}".encode("utf-8")
    context = SourceContext(
        "A", "synthetic", "authored", "common/governments/limit.txt",
        hashlib.sha256(source).hexdigest(),
    )
    return source, context


def _governments(count: int, *, with_name: bool = False) -> str:
    return " ".join(
        f"gov_{i} = {{ name = gov_{i}_name }}" if with_name
        else f"gov_{i} = {{}}"
        for i in range(count)
    )


@pytest.mark.parametrize("count", (LIMIT - 1, LIMIT, LIMIT + 200))
def test_government_child_budget_boundary_stops_candidate_building(count: int):
    source, context = _fixture(_governments(count))
    parsed = parse_bytes(source)
    assert not parsed.diagnostics
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = domain.adapt_domain(parsed, source, context, "government")

    expected_calls = min(count, LIMIT)
    assert make.call_count == expected_calls, (
        f"created={make.call_count}; bound={LIMIT}; blocked={result.blocked}; "
        f"diagnostics={len(result.diagnostics)}; returned_candidates={len(result.candidates)}"
    )
    assert result.blocked is (count >= LIMIT)
    if count < LIMIT:
        assert len(result.candidates) == count
        assert len(result.diagnostics) == count
        assert not result.complete
        assert all(c.resolution == "partial" for c in result.candidates)
    else:
        assert not result.candidates and not result.complete
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "LIMIT_EXCEEDED"


@pytest.mark.parametrize("count", (LIMIT - 1, LIMIT, LIMIT + 200))
def test_government_unsupported_scalar_children_consume_budget(count: int):
    source, context = _fixture(" ".join(f"stray_{i}" for i in range(count)))
    parsed = parse_bytes(source)
    assert not parsed.diagnostics
    with patch.object(domain, "_raw_node", wraps=domain._raw_node) as raw_node:
        result = domain.adapt_domain(parsed, source, context, "government")

    # There are no definition candidates; each unsupported child projects one
    # RawNodeRef and contributes one DOMAIN_UNSUPPORTED_TOP_LEVEL diagnostic.
    assert raw_node.call_count == min(count, LIMIT), (
        f"created_raw={raw_node.call_count}; bound={LIMIT}; "
        f"blocked={result.blocked}; diagnostics={len(result.diagnostics)}"
    )
    assert not result.candidates
    assert result.blocked is (count >= LIMIT)
    if count < LIMIT:
        assert len(result.unhandled) == count
        assert len(result.diagnostics) == count
        assert all(d.code == "DOMAIN_UNSUPPORTED_TOP_LEVEL" for d in result.diagnostics)
    else:
        assert not result.unhandled
        assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]


def test_government_mixed_unsupported_and_candidates_share_one_budget():
    source, ctx = _fixture(
        " ".join(f"stray_{i}" for i in range(250)) + " " + _governments(LIMIT)
    )
    parsed = parse_bytes(source)
    assert not parsed.diagnostics
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = domain.adapt_domain(parsed, source, ctx, "government")
    assert result.blocked and not result.candidates and not result.unhandled
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert make.call_count == LIMIT - 250


def test_government_parser_and_adapter_diagnostics_share_one_budget():
    source, ctx = _fixture("bad ^ = 2 " + _governments(LIMIT + 200))
    parsed = parse_bytes(source)
    assert [d.code for d in parsed.diagnostics] == ["PARSE_UNKNOWN_SYNTAX"]
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = domain.adapt_domain(parsed, source, ctx, "government")
    assert result.blocked and not result.candidates
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert make.call_count == LIMIT - len(parsed.diagnostics) - 1


def test_government_many_diagnostic_free_definitions_keep_all_candidates():
    source, ctx = _fixture(_governments(LIMIT + 200, with_name=True))
    result = domain.adapt_domain(parse_bytes(source), source, ctx, "government")
    assert result.complete and not result.blocked and not result.diagnostics
    assert len(result.candidates) == LIMIT + 200
    assert [c.game_id for c in result.candidates[:2]] == ["gov_0", "gov_1"]
    assert result.candidates[-1].game_id == "gov_1199"
    assert domain.verify_domain_candidate(result.candidates[0], source, ctx)
    assert domain.verify_domain_candidate(result.candidates[-1], source, ctx)


def test_government_duplicate_ids_remain_ambiguous_without_precedence():
    source, ctx = _fixture(
        "same_gov = { name = first_name } same_gov = { name = second_name }"
    )
    result = domain.adapt_domain(parse_bytes(source), source, ctx, "government")
    assert not result.blocked and not result.complete
    assert [c.definition_occurrence for c in result.candidates] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in result.candidates)
    assert all(domain.verify_domain_candidate(c, source, ctx) for c in result.candidates)


def test_government_r1_field_backing_and_r2_foreign_parse_still_rejected():
    source, ctx = _fixture("gov_x = { name = x_name cost = 100 }")
    good = domain.adapt_domain(parse_bytes(source), source, ctx, "government")
    candidate = good.candidates[0]
    cost = next(field for field in candidate.fields if field.name == "cost")
    assert cost.value is not None
    altered = source.replace(b"100", b"999")
    forged_field = replace(cost, value=replace(cost.value, _source=altered))
    forged = replace(
        candidate,
        fields=tuple(forged_field if f == cost else f for f in candidate.fields),
    )
    assert forged.fields[-1].raw_value == "999"
    assert forged.fields[-1].value.source_ref.raw_bytes(source) == b"100"
    assert domain.verify_domain_candidate(candidate, source, ctx)
    assert not domain.verify_domain_candidate(forged, source, ctx)
    with pytest.raises(ValueError, match="ParseResult"):
        domain.adapt_domain(parse_bytes(b""), source, ctx, "government")


def test_government_hard_parser_stop_keeps_empty_result():
    source, ctx = _fixture("gov_x = { name = x_name nested = { depth = 1 } }")
    result = domain.adapt_domain(
        parse_bytes(source, max_depth=1), source, ctx, "government"
    )
    assert result.blocked and not result.candidates and not result.complete
    assert any(d.code == "PARSE_DEPTH_LIMIT" for d in result.diagnostics)
