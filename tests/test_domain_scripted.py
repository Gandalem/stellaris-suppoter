"""TASK-014 Phase C2 authored-synthetic scripted trigger/effect regressions.

This is not evidence of installed Stellaris grammar or engine evaluation.
Existing eleven adapters, R1/R2 source protection and 1,000 diagnostics stay.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain import generic as domain
from stellaris_supporter.domain.generic import (
    adapt_domain,
    find_domain_collisions,
    resolve_domain_name,
    verify_domain_candidate,
)
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.localisation import build_localisation_catalog
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

KINDS = ("scripted_trigger", "scripted_effect")
PREVIOUS_KINDS = (
    "component_template", "building", "district", "pop_job", "trait",
    "government", "civic", "origin", "tradition", "ascension_perk", "event",
)
PREFIXES = {
    "scripted_trigger": "common/scripted_triggers/",
    "scripted_effect": "common/scripted_effects/",
}
LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS


def sample(kind: str, game_id: str = "authored_rule", body: str = "") -> str:
    if kind == "scripted_trigger":
        return (
            f"{game_id} = {{ limit = {{ has_country_flag = active }} "
            f"AND = {{ always = yes custom_trigger = @dynamic }} "
            f"weight = 100 {body} }}"
        )
    assert kind == "scripted_effect"
    return (
        f"{game_id} = {{ if = {{ limit = {{ has_country_flag = active }} "
        f"add_modifier = {{ modifier = @dynamic }} }} "
        f"random = {{ chance = 50 set_country_flag = activated }} "
        f"weight = 100 {body} }}"
    )


def ctx(kind: str, raw: bytes, *, snapshot: str = "A", file: str = "wave5.txt"):
    return SourceContext(
        snapshot, "synthetic", "authored", PREFIXES[kind] + file,
        hashlib.sha256(raw).hexdigest(),
    )


def adapted(
    kind: str, text: str, *, snapshot: str = "A", file: str = "wave5.txt"
):
    raw = text.encode("utf-8")
    context = ctx(kind, raw, snapshot=snapshot, file=file)
    return raw, context, adapt_domain(parse_bytes(raw), raw, context, kind)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_opt_in_registry_preserves_existing_eleven(kind: str):
    assert all(name in domain.DOMAIN_REGISTRY for name in PREVIOUS_KINDS)
    spec = domain.DOMAIN_REGISTRY[kind]
    assert spec.kind == kind and spec.path_prefix == PREFIXES[kind]
    assert spec.id_rule == "root_identifier"
    assert spec.wrapper is None
    assert spec.localisation_rule == "none"


@pytest.mark.parametrize("kind", KINDS)
def test_c2_static_top_level_id_nested_order_and_provenance(kind: str):
    raw, context, result = adapted(
        kind, sample(kind, body="weight = 200 potential = { check = yes }")
    )
    assert result.ok and result.complete and not result.blocked
    assert len(result.candidates) == 1 and not result.unhandled
    c = result.candidates[0]
    assert (c.game_id, c.kind, c.definition_occurrence) == (
        "authored_rule", kind, 1
    )
    assert (c.resolution, c.support_level) == (
        "raw_definition", "synthetic_static"
    )
    assert c.source_ref.raw_bytes(raw).startswith(b"authored_rule =")
    assert c.id_source_ref is not None
    assert c.id_source_ref.raw_bytes(raw) == b"authored_rule"
    assert (c.source_ref.snapshot_id, c.source_ref.relative_path) == (
        context.snapshot_id, context.relative_path
    )
    assert [f.raw_value for f in c.fields if f.name == "weight"] == [
        "100", "200"
    ]
    assert [f.occurrence for f in c.fields if f.name == "weight"] == [1, 2]
    assert any(f.name == "potential" for f in c.conditions)
    assert verify_domain_candidate(c, raw, context)
    serialized = result.to_dict(include_raw=True, max_raw_bytes=100_000)
    assert serialized["candidates"][0]["kind"] == kind
    assert serialized["candidates"][0]["localisation_key"] is None


@pytest.mark.parametrize("kind", KINDS)
def test_c2_scripted_domains_never_invent_localisation_keys(kind: str):
    raw, context, result = adapted(
        kind, sample(kind, body="name = fake_name title = fake_title")
    )
    assert result.complete and len(result.candidates) == 1
    c = result.candidates[0]
    assert c.localisation_key is None
    assert not any(
        d.code == "DOMAIN_UNRESOLVED_LOCALISATION_KEY"
        for d in result.diagnostics
    )
    with pytest.raises(ValueError, match="localisation key"):
        resolve_domain_name(c, build_localisation_catalog(()), "korean")
    with pytest.raises(ValueError, match="localisation key"):
        resolve_domain_name(c, build_localisation_catalog(()), "english")
    assert verify_domain_candidate(c, raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_duplicate_ids_fields_conditions_and_occurrences(kind: str):
    raw, context, result = adapted(
        kind,
        sample(kind, body="weight = 200 limit = { exists = yes }")
        + "\n" + sample(kind, body="weight = 300 limit = { exists = no }")
    )
    assert not result.complete and len(result.candidates) == 2
    assert [c.game_id for c in result.candidates] == [
        "authored_rule", "authored_rule"
    ]
    assert [c.definition_occurrence for c in result.candidates] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in result.candidates)
    assert [f.raw_value for f in result.candidates[0].fields
            if f.name == "weight"] == ["100", "200"]
    top_level_limits = [
        f for f in result.candidates[0].conditions if f.name == "limit"
    ]
    # The effect's other "limit" lives inside the raw "if" AST; it must
    # NOT become a fabricated second top-level condition.
    assert len(top_level_limits) == (
        2 if kind == "scripted_trigger" else 1
    )
    if kind == "scripted_effect":
        enclosing_if = next(
            f for f in result.candidates[0].conditions if f.name == "if"
        )
        assert "limit = { has_country_flag = active }" in enclosing_if.raw_value
    assert any(d.code == "DOMAIN_DUPLICATE_ID" for d in result.diagnostics)
    assert all(verify_domain_candidate(c, raw, context) for c in result.candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_cross_file_duplicate_id_collision_and_snapshot_separation(kind: str):
    raw, context, left = adapted(kind, sample(kind), file="first.txt")
    _, _, right = adapted(kind, sample(kind), file="second.txt")
    collision = find_domain_collisions((*left.candidates, *right.candidates))
    assert len(collision) == 1
    assert len(collision[0].definition_source_refs) == 2
    assert collision[0].definition_source_refs[0].relative_path.endswith(
        "first.txt"
    )
    assert collision[0].definition_source_refs[1].relative_path.endswith(
        "second.txt"
    )
    c = left.candidates[0]
    assert not verify_domain_candidate(
        c, raw, replace(context, relative_path=PREFIXES[kind] + "other.txt")
    )
    assert not verify_domain_candidate(
        c, raw, replace(context, snapshot_id="B")
    )
    _, _, foreign = adapted(kind, sample(kind), snapshot="B")
    with pytest.raises(ValueError, match="snapshot"):
        find_domain_collisions((*left.candidates, *foreign.candidates))


def test_c2_identical_id_different_scripted_kinds_not_a_conflict():
    same = tuple(adapted(kind, sample(kind))[2].candidates[0] for kind in KINDS)
    assert not find_domain_collisions(same)
    assert all(c.localisation_key is None for c in same)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_dynamic_root_key_and_unsupported_wrapper_never_guessed(kind: str):
    for source in (
        "@dynamic = { limit = { flag = yes } }",
        "123 = { limit = { flag = yes } }",
        "scripted > { limit = { flag = yes } }",
    ):
        raw, context, result = adapted(kind, source)
        assert not result.candidates or any(
            c.resolution == "partial" for c in result.candidates
        )
        assert result.unhandled or not result.complete
        if result.unhandled:
            assert all(x.source_ref.raw_bytes(raw) for x in result.unhandled)
    with pytest.raises(ValueError, match="source path"):
        raw = sample(kind).encode()
        adapt_domain(
            parse_bytes(raw), raw,
            replace(ctx(kind, raw), relative_path="common/other/not_scripted.txt"),
            kind,
        )


@pytest.mark.parametrize("kind", KINDS)
def test_c2_operator_unknown_unclosed_and_comment_string_are_lossless(kind: str):
    source = sample(kind, body='cost > 99 unknown ^ = 3 note = "fake = { }"')
    raw, _, partial = adapted(kind, source)
    assert not partial.complete and len(partial.candidates) == 1
    codes = {d.code for d in partial.diagnostics}
    assert "DOMAIN_UNSUPPORTED_OPERATOR" in codes
    assert "PARSE_UNKNOWN_SYNTAX" in codes
    assert "DOMAIN_UNKNOWN_STRUCTURE" in codes
    assert any("fake = { }" in f.raw_value
               for f in partial.candidates[0].fields
               if f.name == "note")
    _, _, unclosed = adapted(kind, sample(kind)[:-2])
    assert not unclosed.complete
    assert "PARSE_UNCLOSED_BLOCK" in {d.code for d in unclosed.diagnostics}
    raw, context, clean = adapted(
        kind, sample(kind) + "\n# fake_rule = { id = false }"
    )
    assert clean.complete and len(clean.candidates) == 1
    assert verify_domain_candidate(clean.candidates[0], raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_r1_raw_backing_fields_conditions_recursive_child_and_loan(kind: str):
    raw, context, result = adapted(
        kind, sample(kind, body="cost = 100 cost = 100 limit = { deep = yes }")
    )
    c = result.candidates[0]
    cost = [f for f in c.fields if f.name == "cost"]
    assert len(cost) == 2 and cost[0].value is not None
    forged_bytes = raw.replace(b"100", b"999")
    tampered = replace(cost[0], value=replace(cost[0].value, _source=forged_bytes))
    assert not verify_domain_candidate(
        replace(c, fields=tuple(tampered if f is cost[0] else f for f in c.fields)),
        raw, context
    )
    conditions = [f for f in c.conditions if f.name == "limit"]
    assert conditions and conditions[0].value is not None
    cond = conditions[-1]
    bad = raw.replace(b"yes", b"bad")
    assert not verify_domain_candidate(
        replace(c, conditions=tuple(
            replace(f, value=replace(f.value, _source=bad))
            if f is cond else f for f in c.conditions
        )), raw, context
    )
    assert cond.value.children
    replaced_child = replace(cond.value.children[0], _source=bad)
    new_cond = replace(cond, value=replace(
        cond.value, children=(replaced_child, *cond.value.children[1:])
    ))
    assert not verify_domain_candidate(
        replace(c, conditions=tuple(new_cond if f is cond else f for f in c.conditions)),
        raw, context
    )
    swapped_ref = replace(cost[0], source_ref=cost[1].source_ref)
    assert not verify_domain_candidate(
        replace(c, fields=tuple(swapped_ref if f is cost[0] else f for f in c.fields)),
        raw, context
    )
    assert verify_domain_candidate(c, raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_r2_full_parse_ast_coordinates_hash_and_context(kind: str):
    raw, context, normal = adapted(kind, sample(kind))
    parsed = parse_bytes(raw)
    malformed = (
        parse_bytes(b""),
        replace(parsed, document=replace(parsed.document, items=())),
        replace(parsed, tokens=(
            replace(parsed.tokens[0], span=replace(parsed.tokens[0].span, line_start=77)),
            *parsed.tokens[1:],
        )),
        replace(parsed, document=replace(parsed.document, items=(
            replace(parsed.document.items[0], span=replace(
                parsed.document.items[0].span, column_start=99
            )), *parsed.document.items[1:]
        ))),
    )
    for foreign in malformed:
        with pytest.raises(ValueError, match="ParseResult"):
            adapt_domain(foreign, raw, context, kind)
    with pytest.raises(ValueError, match="hash"):
        adapt_domain(
            parsed, raw, replace(context, file_sha256="0" * 64), kind
        )
    assert verify_domain_candidate(normal.candidates[0], raw, context)


@pytest.mark.parametrize("kind", KINDS)
def test_c2_bom_crlf_hangul_bytes_and_encoding_hard_limits(kind: str):
    source = "\ufeff" + sample(
        kind, body='note = "한글 {} # ="\r\n extra = 8'
    ).replace(" weight", "\r\n weight")
    raw, context, result = adapted(kind, source)
    assert result.complete and result.candidates
    c = result.candidates[0]
    assert c.id_source_ref.raw_bytes(raw) == b"authored_rule"
    assert next(f for f in c.fields if f.name == "note").raw_value == (
        '"한글 {} # ="'
    )
    assert verify_domain_candidate(c, raw, context)
    with pytest.raises(ValueError):
        result.to_dict(include_raw=True, max_raw_bytes=1)
    invalid = b"\xff"
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(parse_bytes(b""), invalid, ctx(kind, invalid), kind)
    failclosed = adapt_domain(
        parse_bytes(invalid), invalid, ctx(kind, invalid), kind
    )
    assert failclosed.blocked and not failclosed.candidates
    for limited in (
        parse_bytes(raw, max_tokens=2),
        parse_bytes(raw, max_nodes=2),
        parse_bytes(raw, max_depth=1),
    ):
        r = adapt_domain(limited, raw, context, kind)
        assert r.blocked and not r.candidates and not r.complete


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("count", (LIMIT - 1, LIMIT, LIMIT + 200))
def test_c2_diagnostic_budget_boundary_inclusive(kind: str, count: int):
    source = "\n".join(f"rule_{i} = value" for i in range(count))
    raw, context = source.encode(), ctx(kind, source.encode())
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = adapt_domain(parse_bytes(raw), raw, context, kind)
    assert make.call_count == min(count, LIMIT)
    assert result.blocked is (count >= LIMIT)
    if count < LIMIT:
        assert len(result.candidates) == count
        assert len(result.diagnostics) == count
        assert not result.complete
    else:
        assert not result.candidates and not result.complete
        assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]


@pytest.mark.parametrize("kind", KINDS)
def test_c2_1200_clean_definitions_and_parser_diagnostic_budget(kind: str):
    count = LIMIT + 200
    source = "\n".join(f"rule_{i} = {{ flag = yes }}" for i in range(count))
    raw, context, result = adapted(kind, source)
    assert result.complete and not result.diagnostics
    assert len(result.candidates) == count
    assert verify_domain_candidate(result.candidates[0], raw, context)
    assert verify_domain_candidate(result.candidates[-1], raw, context)
    source = "bad ^ = 2\n" + "\n".join(
        f"rule_{i} = yes" for i in range(count)
    )
    raw, context = source.encode(), ctx(kind, source.encode())
    parsed = parse_bytes(raw)
    assert any(d.code == "PARSE_UNKNOWN_SYNTAX" for d in parsed.diagnostics)
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        blocked = adapt_domain(parsed, raw, context, kind)
    assert blocked.blocked and not blocked.candidates
    assert make.call_count < LIMIT


@pytest.mark.parametrize("kind", KINDS)
def test_c2_single_candidate_bad_field_budget_bounded_before_raw(kind: str):
    source = sample(
        kind, body=" ".join(f"bad_{i} > yes" for i in range(LIMIT + 200))
    )
    raw, context = source.encode(), ctx(kind, source.encode())
    parsed = parse_bytes(raw)
    assert not parsed.diagnostics
    with patch.object(domain, "_raw_node", wraps=domain._raw_node) as raw_node:
        result = adapt_domain(parsed, raw, context, kind)
    assert result.blocked and not result.candidates
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert raw_node.call_count <= LIMIT


@pytest.mark.parametrize("kind", KINDS)
def test_c2_exact_canonical_parse_once_per_file_and_per_verify(kind: str):
    raw, context, result = adapted(
        kind, sample(kind, "first") + "\n" + sample(kind, "second")
    )
    assert len(result.candidates) == 2
    with patch.object(domain, "parse_bytes", wraps=parse_bytes) as parsed:
        again = adapt_domain(parse_bytes(raw), raw, context, kind)
        assert len(again.candidates) == 2
    assert parsed.call_count == 1
    with patch.object(domain, "parse_bytes", wraps=parse_bytes) as parsed:
        assert all(
            verify_domain_candidate(c, raw, context)
            for c in result.candidates
        )
    assert parsed.call_count == 2
