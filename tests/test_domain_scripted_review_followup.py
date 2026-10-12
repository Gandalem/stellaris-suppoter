"""PR #33 R1/P2: scripted PairNode variable KEY source-binding regression.

All fixtures below are authored synthetic data, not Stellaris engine grammar.
Commit these tests first; verify their pre-fix failures before editing generic.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain import generic as domain
from stellaris_supporter.domain.generic import adapt_domain, verify_domain_candidate
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import BlockNode, PairNode, parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

KINDS = ("scripted_trigger", "scripted_effect")
PATHS = {
    "scripted_trigger": "common/scripted_triggers/",
    "scripted_effect": "common/scripted_effects/",
}
LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS


def fixture(
    kind: str, text: str, *, snapshot: str = "A", file: str = "r1_key.txt"
):
    raw = text.encode("utf-8")
    context = SourceContext(
        snapshot, "synthetic", "authored", PATHS[kind] + file,
        hashlib.sha256(raw).hexdigest(),
    )
    parsed = parse_bytes(raw)
    return raw, context, parsed, adapt_domain(parsed, raw, context, kind)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("key", ("@dynamic", "@variable"))
@pytest.mark.parametrize(
    "placement",
    (
        "direct",
        "nested",
        "deeply_nested",
    ),
)
def test_r1_scripted_variable_pair_key_is_partial_with_exact_key_span(
    kind: str, key: str, placement: str
):
    expression = f"{key} = yes"
    wrapped = {
        "direct": expression,
        "nested": f"nested = {{ {expression} }}",
        "deeply_nested": f"outer = {{ nested = {{ {expression} }} }}",
    }[placement]
    source = (
        "authored_rule = { flag = one "
        + wrapped
        + " flag = two name = raw_only }"
    )
    raw, context, parsed, result = fixture(kind, source)

    # Prove lexer/parser construction: this is truly a variable PairNode key,
    # not a string or a variable ScalarNode in a value position.
    def variable_pairs(node):
        if isinstance(node, PairNode):
            if node.key_kind == "variable":
                yield node
            if node.value is not None:
                yield from variable_pairs(node.value)
        elif isinstance(node, BlockNode):
            for item in node.items:
                yield from variable_pairs(item)

    matching = [p for p in variable_pairs(parsed.document.items[0]) if p.key_text == key]
    assert len(matching) == 1
    assert matching[0].key_kind == "variable"
    assert raw[matching[0].key_span.byte_start:matching[0].key_span.byte_end] == key.encode()

    assert not result.blocked and len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.kind == kind and candidate.game_id == "authored_rule"
    assert candidate.id_source_ref is not None
    assert candidate.id_source_ref.raw_bytes(raw) == b"authored_rule"
    assert candidate.localisation_key is None
    assert (candidate.resolution, candidate.support_level, result.complete) == (
        "partial", "partial", False
    )
    warnings = [
        d for d in result.diagnostics
        if d.code == "DOMAIN_DYNAMIC_EXPRESSION_UNSUPPORTED"
    ]
    assert len(warnings) == 1
    assert warnings[0].source_ref.raw_bytes(raw) == key.encode("ascii")
    assert (
        warnings[0].source_ref.byte_start,
        warnings[0].source_ref.byte_end,
    ) == (
        matching[0].key_span.byte_start,
        matching[0].key_span.byte_end,
    )
    assert warnings[0].source_ref.snapshot_id == context.snapshot_id
    assert warnings[0].source_ref.relative_path == context.relative_path
    assert warnings[0].source_ref.file_sha256 == context.file_sha256

    # The fully ordered definition, duplicate occurrences, nested raw bytes,
    # independent nested children, and SourceRefs remain untouched.
    assert [f.raw_value for f in candidate.fields if f.name == "flag"] == [
        "one", "two"
    ]
    assert [f.occurrence for f in candidate.fields if f.name == "flag"] == [1, 2]
    if placement == "direct":
        assert any(f.name == key and f.raw_value == "yes" for f in candidate.fields)
    else:
        assert wrapped.encode() in candidate.source_ref.raw_bytes(raw)
        assert any(key in f.raw_value for f in candidate.fields if f.raw_value)
    assert len(candidate.items) == 4
    assert all(item.raw_bytes() == item.source_ref.raw_bytes(raw)
               for item in candidate.items)
    assert verify_domain_candidate(candidate, raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_r1_scripted_value_dynamic_behavior_still_source_grounded(kind: str):
    raw, context, _, result = fixture(
        kind, "authored_rule = { runtime = @dynamic }"
    )
    assert not result.blocked and not result.complete
    assert result.candidates[0].resolution == "partial"
    diagnostics = [
        d for d in result.diagnostics
        if d.code == "DOMAIN_DYNAMIC_EXPRESSION_UNSUPPORTED"
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0].source_ref.raw_bytes(raw) == b"@dynamic"
    assert verify_domain_candidate(result.candidates[0], raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_r1_scripted_quoted_variable_key_and_comment_are_not_dynamic(kind: str):
    source = (
        'authored_rule = { "@dynamic" = yes note = "@variable" }'
        "\n# @dynamic = yes, @variable = no"
    )
    raw, context, parsed, result = fixture(kind, source)
    assert not result.blocked and result.complete
    assert len(result.candidates) == 1 and not result.diagnostics
    pair = parsed.document.items[0]
    assert isinstance(pair, PairNode) and isinstance(pair.value, BlockNode)
    quoted = pair.value.items[0]
    assert isinstance(quoted, PairNode) and quoted.key_kind == "string"
    assert quoted.key_text == '"@dynamic"'
    assert result.candidates[0].fields[0].raw_value == "yes"
    assert result.candidates[0].fields[1].raw_value == '"@variable"'
    assert verify_domain_candidate(result.candidates[0], raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_r1_scripted_variable_key_raw_backing_and_r2_foreign_parse(kind: str):
    raw, context, parsed, result = fixture(
        kind, "authored_rule = { nested = { @dynamic = yes } number = 100 }"
    )
    candidate = result.candidates[0]
    assert candidate.source_ref.raw_bytes(raw).endswith(b"number = 100 }")
    assert verify_domain_candidate(candidate, raw, context)

    corrupted = raw.replace(b"@dynamic", b"@altered")  # same byte length
    nested = candidate.fields[0]
    assert nested.value is not None and nested.value.children
    projected = replace(
        nested, value=replace(nested.value, _source=corrupted)
    )
    forged = replace(
        candidate,
        fields=(projected, *candidate.fields[1:]),
    )
    assert not verify_domain_candidate(forged, raw, context)
    forged_child = replace(
        nested.value.children[0], _source=corrupted
    )
    changed_nested = replace(
        nested, value=replace(nested.value, children=(forged_child, *nested.value.children[1:]))
    )
    assert not verify_domain_candidate(
        replace(candidate, fields=(changed_nested, *candidate.fields[1:])),
        raw, context,
    )

    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(parse_bytes(b""), raw, context, kind)
    forged_tokens = replace(
        parsed, tokens=(
            replace(
                parsed.tokens[0],
                span=replace(parsed.tokens[0].span, line_start=12),
            ),
            *parsed.tokens[1:],
        )
    )
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(forged_tokens, raw, context, kind)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("count", (LIMIT - 1, LIMIT, LIMIT + 200))
def test_r1_scripted_dynamic_key_warning_shared_diagnostic_limit(
    kind: str, count: int
):
    source = "\n".join(
        f"rule_{i} = {{ @dynamic = yes }}" for i in range(count)
    )
    raw, context, parsed, result = fixture(kind, source)
    assert result.blocked is (count >= LIMIT)
    if count < LIMIT:
        assert len(result.candidates) == count
        assert len(result.diagnostics) == count
        assert all(c.resolution == "partial" for c in result.candidates)
    else:
        assert not result.candidates and not result.complete
        assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    # The original parser and adapter limits remain shared; no raised budget.
    assert len(parsed.diagnostics) <= LIMIT


@pytest.mark.parametrize("kind", KINDS)
def test_r1_scripted_parser_plus_variable_key_warning_budget(kind: str):
    source = (
        "bad ^ = 2\n"
        + "\n".join(f"rule_{i} = {{ @dynamic = yes }}" for i in range(LIMIT + 200))
    )
    raw, context, parsed, _ = fixture(kind, source)
    assert parsed.diagnostics
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = adapt_domain(parsed, raw, context, kind)
    assert result.blocked and not result.candidates
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert make.call_count < LIMIT
