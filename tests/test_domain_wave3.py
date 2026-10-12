"""TASK-014 Phase B: authored synthetic tradition and ascension-perk grammars.

These opt-in fixtures are not verified Stellaris game data or engine rules.
Commit red tests before extending DOMAIN_REGISTRY; retain Phase A regressions.
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
from stellaris_supporter.localisation import build_localisation_catalog, parse_localisation
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

KINDS = ("tradition", "ascension_perk")
BASELINE_KINDS = (
    "component_template", "building", "district", "pop_job",
    "trait", "government", "civic", "origin",
)
PATHS = {
    "tradition": "common/traditions/",
    "ascension_perk": "common/ascension_perks/",
}
LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS


def sample(kind: str, *, game_id: str = "shared_x", body: str = "") -> str:
    extra = f"name = {game_id}_name cost = 100 potential = {{ flag = yes }} {body}"
    if kind == "tradition":
        return f"traditions = {{ {game_id} = {{ {extra} }} }}"
    if kind == "ascension_perk":
        return f"ascension_perk = {{ id = {game_id} {extra} }}"
    raise AssertionError("unregistered test kind")


def context(kind: str, raw: bytes, *, snapshot: str = "A", file: str = "wave3.txt"):
    return SourceContext(
        snapshot, "synthetic", "authored", PATHS[kind] + file,
        hashlib.sha256(raw).hexdigest(),
    )


def adapted(
    kind: str, value: str, *, snapshot: str = "A", file: str = "wave3.txt"
):
    raw = value.encode()
    ctx = context(kind, raw, snapshot=snapshot, file=file)
    result = adapt_domain(parse_bytes(raw), raw, ctx, kind)
    return raw, ctx, result


def loc_document(raw: bytes, *, language: str = "english", snapshot: str = "A"):
    return parse_localisation(
        raw,
        SourceContext(
            snapshot, "synthetic", "authored",
            f"localisation/{language}/wave3_l_{language}.yml",
            hashlib.sha256(raw).hexdigest(),
        ),
    )


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_registry_extends_exact_eight_original_kinds(kind: str):
    assert all(name in domain.DOMAIN_REGISTRY for name in BASELINE_KINDS)
    spec = domain.DOMAIN_REGISTRY[kind]
    assert spec.path_prefix == PATHS[kind]
    assert spec.localisation_rule == "name_field"
    assert spec.id_rule == (
        "nested_identifier" if kind == "tradition" else "literal_id_field"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_exact_source_spans_ids_and_distinct_localisation(kind: str):
    raw, ctx, result = adapted(
        kind, sample(kind, body="effect = { unity = @dynamic }")
    )
    assert result.complete and result.ok and not result.blocked
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert (c.kind, c.game_id, c.definition_occurrence) == (kind, "shared_x", 1)
    assert (c.resolution, c.support_level) == ("raw_definition", "synthetic_static")
    assert c.localisation_key == "shared_x_name"
    assert c.id_source_ref is not None
    assert c.id_source_ref.raw_bytes(raw) == b"shared_x"
    assert c.source_ref.raw_bytes(raw).startswith(
        b"shared_x =" if kind == "tradition" else b"ascension_perk ="
    )
    assert c.source_ref.relative_path == ctx.relative_path
    assert [f.raw_value for f in c.conditions] == ["{ flag = yes }"]
    assert next(f for f in c.fields if f.name == "effect").raw_value == (
        "{ unity = @dynamic }"
    )
    assert verify_domain_candidate(c, raw, ctx)
    assert result.to_dict(include_raw=False)["candidates"][0]["kind"] == kind


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_wrappers_and_unverified_group_forms_are_not_ids(kind: str):
    if kind == "tradition":
        texts = (
            "tradition_tree = { tree_a = { tr_a = {} } }",
            "tradition = { id = tr_a }",
            "not_traditions = { tr_a = {} }",
        )
    else:
        texts = (
            "ascension_perks = { perk_a = { id = perk_a } }",
            "perk_a = { id = perk_a }",
            "traditions = { perk_a = {} }",
        )
    for value in texts:
        raw, _, result = adapted(kind, value)
        assert not result.candidates and not result.complete
        assert result.unhandled and all(
            item.source_ref.raw_bytes(raw) for item in result.unhandled
        )
        assert any(
            diagnostic.code == "DOMAIN_UNSUPPORTED_TOP_LEVEL"
            for diagnostic in result.diagnostics
        )


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_missing_dynamic_duplicate_ids_not_guessed(kind: str):
    if kind == "tradition":
        cases = (
            "traditions = { @variable = { name = bad_name } }",
            "traditions = { 123 = { name = bad_name } }",
        )
        for value in cases:
            _, _, result = adapted(kind, value)
            assert not result.complete and result.unhandled
            assert not result.candidates
    else:
        for fragment in (
            "", "id = @dynamic", "id = shared_x id = second",
            "id > shared_x", "id = { variable = x }",
        ):
            _, _, result = adapted(
                kind, sample(kind).replace("id = shared_x", fragment)
            )
            assert len(result.candidates) == 1
            c = result.candidates[0]
            assert c.game_id is None and c.id_source_ref is None
            assert c.resolution == "partial"
            assert any(d.code == "DOMAIN_UNRESOLVED_ID" for d in c.diagnostics)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "name_fragment", ("", "name = @dynamic", "name = one name = two")
)
def test_wave3_localisation_key_requires_unique_static_name(
    kind: str, name_fragment: str
):
    _, _, result = adapted(
        kind, sample(kind).replace("name = shared_x_name", name_fragment)
    )
    c = result.candidates[0]
    assert c.game_id == "shared_x"
    assert c.localisation_key is None and c.resolution == "partial"
    assert any(
        d.code == "DOMAIN_UNRESOLVED_LOCALISATION_KEY" for d in c.diagnostics
    )
    with pytest.raises(ValueError, match="localisation key"):
        resolve_domain_name(c, build_localisation_catalog(()))


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_duplicate_fields_definitions_conditions_preserve_occurrence(kind: str):
    first = sample(
        kind, body="cost = 200 potential = { allowed = yes } "
        "effect = { science = @dynamic }",
    )
    second = sample(kind, body="cost = 300")
    raw, ctx, result = adapted(kind, first + "\n" + second)
    assert [c.game_id for c in result.candidates] == ["shared_x", "shared_x"]
    assert [c.definition_occurrence for c in result.candidates] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in result.candidates)
    assert [f.raw_value for f in result.candidates[0].fields if f.name == "cost"] == [
        "100", "200",
    ]
    assert [f.occurrence for f in result.candidates[0].fields if f.name == "cost"] == [1, 2]
    assert len(result.candidates[0].conditions) == 2
    assert any(d.code == "DOMAIN_DUPLICATE_ID" for d in result.diagnostics)
    assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_cross_file_collisions_and_snapshot_separation(kind: str):
    raw, ctx, left = adapted(kind, sample(kind), file="one.txt")
    _, _, right = adapted(kind, sample(kind, body="cost = 200"), file="two.txt")
    c = find_domain_collisions((*left.candidates, *right.candidates))
    assert len(c) == 1 and len(c[0].definition_source_refs) == 2
    assert c[0].definition_source_refs[0].relative_path.endswith("one.txt")
    assert c[0].definition_source_refs[1].relative_path.endswith("two.txt")
    assert not verify_domain_candidate(
        left.candidates[0], raw, replace(ctx, relative_path=PATHS[kind] + "two.txt")
    )
    assert not verify_domain_candidate(left.candidates[0], raw, replace(ctx, snapshot_id="B"))
    _, _, foreign = adapted(kind, sample(kind), snapshot="B")
    with pytest.raises(ValueError, match="snapshot"):
        find_domain_collisions((*left.candidates, *foreign.candidates))


def test_wave3_same_id_in_distinct_kinds_never_collides():
    candidates = tuple(
        adapted(kind, sample(kind))[2].candidates[0] for kind in KINDS
    )
    assert all(c.game_id == "shared_x" for c in candidates)
    assert not find_domain_collisions(candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_r1_raw_backing_field_condition_child_and_same_file_loan(kind: str):
    raw, ctx, result = adapted(
        kind, sample(kind, body="cost = 100 potential = { nested = yes }")
    )
    c = result.candidates[0]
    cost = next(f for f in c.fields if f.name == "cost")
    assert cost.value is not None
    alternate = raw.replace(b"100", b"999")
    forged_cost = replace(cost, value=replace(cost.value, _source=alternate))
    changed_fields = tuple(forged_cost if f is cost else f for f in c.fields)
    assert not verify_domain_candidate(replace(c, fields=changed_fields), raw, ctx)
    potential = c.conditions[0]
    assert potential.value is not None and potential.value.children
    different = raw.replace(b"yes", b"no!")
    modified_condition = replace(
        potential, value=replace(potential.value, _source=different)
    )
    assert not verify_domain_candidate(
        replace(c, conditions=(modified_condition,)), raw, ctx
    )
    modified_child = replace(potential.value.children[0], _source=different)
    modified_nested = replace(
        potential, value=replace(potential.value, children=(modified_child,))
    )
    assert not verify_domain_candidate(
        replace(c, conditions=(modified_nested,)), raw, ctx
    )

    for corrupted in (
        replace(c, definition_occurrence=2),
        replace(c, fields=tuple(
            replace(f, operator=">") if f is cost else f for f in c.fields
        )),
        replace(c, fields=tuple(
            replace(f, name="price") if f is cost else f for f in c.fields
        )),
        replace(c, source_ref=replace(c.source_ref, byte_end=1)),
        replace(c, id_source_ref=replace(c.id_source_ref, byte_start=0)),
    ):
        assert not verify_domain_candidate(corrupted, raw, ctx)
    assert verify_domain_candidate(c, raw, ctx)

    same, same_ctx, all_defs = adapted(
        kind, sample(kind, body="cost = 100 cost = 100")
    )
    duplicate_cost = [f for f in all_defs.candidates[0].fields if f.name == "cost"]
    assert len(duplicate_cost) >= 2
    orig = all_defs.candidates[0]
    borrowed = replace(
        orig,
        fields=tuple(
            replace(f, source_ref=duplicate_cost[-1].source_ref)
            if f is duplicate_cost[0] else f for f in orig.fields
        ),
    )
    assert not verify_domain_candidate(borrowed, same, same_ctx)


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_r2_foreign_parse_ast_token_coordinates_and_sha(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    parsed = parse_bytes(raw)
    tampered = (
        parse_bytes(b""),
        replace(parsed, document=replace(parsed.document, items=())),
        replace(
            parsed, tokens=(
                replace(parsed.tokens[0], span=replace(
                    parsed.tokens[0].span, line_start=77
                )),
                *parsed.tokens[1:],
            ),
        ),
        replace(
            parsed, document=replace(
                parsed.document,
                items=(
                    replace(
                        parsed.document.items[0],
                        span=replace(parsed.document.items[0].span, column_start=99),
                    ),
                ),
            ),
        ),
    )
    for bad in tampered:
        with pytest.raises(ValueError):
            adapt_domain(bad, raw, ctx, kind)
    with pytest.raises(ValueError, match="hash"):
        adapt_domain(parsed, raw, replace(ctx, file_sha256="0" * 64), kind)
    assert verify_domain_candidate(result.candidates[0], raw, ctx)
    for limit_parse in (
        parse_bytes(raw, max_tokens=2),
        parse_bytes(raw, max_nodes=2),
        parse_bytes(raw, max_depth=1),
    ):
        limited = adapt_domain(limit_parse, raw, ctx, kind)
        assert limited.blocked and not limited.candidates and not limited.complete


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_invalid_utf8_and_bom_crlf_hangul_spans_raw_budget(kind: str):
    source = "\ufeff" + sample(
        kind, body='description = "한글 # {}"\r\n cost = 200'
    ).replace(" cost", "\r\n cost")
    raw, ctx, result = adapted(kind, source)
    assert result.candidates and not result.blocked and result.complete
    c = result.candidates[0]
    assert any(f.raw_value == '"한글 # {}"' for f in c.fields)
    assert c.id_source_ref.raw_bytes(raw) == b"shared_x"
    assert verify_domain_candidate(c, raw, ctx)
    with pytest.raises(ValueError):
        result.to_dict(include_raw=True, max_raw_bytes=1)
    corrupted = b"\xff"
    bad = context(kind, corrupted)
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(parse_bytes(b""), corrupted, bad, kind)
    blocked = adapt_domain(parse_bytes(corrupted), corrupted, bad, kind)
    assert blocked.blocked and not blocked.candidates


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_unclosed_unknown_operators_and_quoted_fake_syntax(kind: str):
    _, _, partial = adapted(kind, sample(kind, body="cost >= 44 unknown ^ = 9"))
    assert not partial.complete
    assert any(d.code == "DOMAIN_UNSUPPORTED_OPERATOR" for d in partial.diagnostics)
    assert any(d.code in {"PARSE_UNKNOWN_SYNTAX", "DOMAIN_UNKNOWN_STRUCTURE"} for d in partial.diagnostics)
    _, _, unclosed = adapted(kind, sample(kind)[:-2])
    assert not unclosed.complete
    assert any(d.code == "PARSE_UNCLOSED_BLOCK" for d in unclosed.diagnostics)
    _, _, safe = adapted(
        kind, sample(kind, body='description = "fake_id = { # }"')
        + "\n# fake_id = { id = fake }",
    )
    assert safe.complete and len(safe.candidates) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_localisation_korean_english_fallback_and_provenance(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    c = result.candidates[0]
    key = c.localisation_key
    assert key == "shared_x_name"
    ko = f'l_korean:\n {key}:0 "한국어 $a$"\n a:0 "$b$"\n b:0 "이름"\n'.encode()
    en = f'l_english:\n {key}:0 "English Name"\n'.encode()
    docs = (
        loc_document(ko, language="korean"),
        loc_document(en),
    )
    catalog = build_localisation_catalog(docs)
    korean = resolve_domain_name(c, catalog, "korean").localisation
    assert korean.display_value == "한국어 이름"
    assert korean.fallback == "none" and korean.language_used == "korean"
    assert korean.source_ref == docs[0].entries[0].source_ref
    assert len(korean.reference_source_refs) == 2
    assert all(x.snapshot_id == ctx.snapshot_id for x in korean.reference_source_refs)
    english = resolve_domain_name(c, catalog, "english").localisation
    assert english.display_value == "English Name" and english.fallback == "none"
    english_only = resolve_domain_name(
        c, build_localisation_catalog((loc_document(en),)), "korean"
    ).localisation
    assert english_only.language_used == "english" and english_only.fallback == "english"
    absent = resolve_domain_name(c, build_localisation_catalog(()), "korean").localisation
    assert absent.resolution == "unresolved" and absent.fallback == "id"
    assert absent.display_value == key and absent.display_value != c.game_id
    with pytest.raises(ValueError, match="snapshot"):
        resolve_domain_name(
            c, build_localisation_catalog((
                loc_document(ko, language="korean", snapshot="B"),
            ))
        )


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_localisation_ambiguous_cycle_dynamic_budget_and_bad_source(kind: str):
    _, _, result = adapted(kind, sample(kind))
    c = result.candidates[0]
    key = c.localisation_key
    dup = f'l_korean:\n {key}:0 "a"\n {key}:0 "b"\n'.encode()
    ambiguous = resolve_domain_name(
        c, build_localisation_catalog((loc_document(dup, language="korean"),))
    ).localisation
    assert ambiguous.resolution == "ambiguous"
    cyclic = f'l_korean:\n {key}:0 "$first$"\n first:0 "$first$"\n'.encode()
    cycle = resolve_domain_name(
        c, build_localisation_catalog((loc_document(cyclic, language="korean"),))
    ).localisation
    assert cycle.resolution == "partial"
    assert any(d.code == "LOC_CYCLE" for d in cycle.diagnostics)
    dynamic = f'l_english:\n {key}:0 "[Root.GetName] £energy£"\n'.encode()
    cat = build_localisation_catalog((loc_document(dynamic),))
    d = resolve_domain_name(c, cat, "english").localisation
    assert d.resolution == "partial"
    assert any(diag.code == "LOC_DYNAMIC_UNSUPPORTED" for diag in d.diagnostics)
    bounded = resolve_domain_name(c, cat, "english", max_scan_bytes=1).localisation
    assert bounded.resolution == "partial" and bounded.truncated
    bad_doc = parse_localisation(
        dynamic, replace(loc_document(dynamic).context, file_sha256="0" * 64)
    )
    compromised = resolve_domain_name(
        c, build_localisation_catalog((bad_doc,)), "english"
    ).localisation
    assert compromised.resolution != "resolved"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("count", (LIMIT - 1, LIMIT, LIMIT + 200))
def test_wave3_diagnostic_budget_stops_at_child_or_root_boundary(kind: str, count: int):
    if kind == "tradition":
        source = "traditions = { " + " ".join(
            f"tr_{i} = {{}}" for i in range(count)
        ) + " }"
    else:
        source = " ".join(
            f"ascension_perk = {{ id = perk_{i} }}" for i in range(count)
        )
    raw, ctx = source.encode(), context(kind, source.encode())
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = adapt_domain(parse_bytes(raw), raw, ctx, kind)
    assert make.call_count == min(count, LIMIT)
    assert result.blocked is (count >= LIMIT)
    if count < LIMIT:
        assert len(result.candidates) == count
        assert len(result.diagnostics) == count
        assert all(c.resolution == "partial" for c in result.candidates)
    else:
        assert not result.candidates and not result.complete
        assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_many_valid_definitions_and_nested_unsupported_budget(kind: str):
    if kind == "tradition":
        source = "traditions = { " + " ".join(
            f"tr_{i} = {{ name = tr_{i}_name }}" for i in range(LIMIT + 200)
        ) + " }"
    else:
        source = " ".join(
            f"ascension_perk = {{ id = perk_{i} name = perk_{i}_name }}"
            for i in range(LIMIT + 200)
        )
    raw, ctx, result = adapted(kind, source)
    assert result.complete and not result.diagnostics
    assert len(result.candidates) == LIMIT + 200
    assert verify_domain_candidate(result.candidates[0], raw, ctx)
    assert verify_domain_candidate(result.candidates[-1], raw, ctx)
    if kind == "tradition":
        unsupported = "traditions = { " + " ".join(
            f"stray_{i}" for i in range(LIMIT + 200)
        ) + " }"
        raw, ctx = unsupported.encode(), context(kind, unsupported.encode())
        with patch.object(domain, "_raw_node", wraps=domain._raw_node) as raw_node:
            blocked = adapt_domain(parse_bytes(raw), raw, ctx, kind)
        assert blocked.blocked and not blocked.candidates
        assert raw_node.call_count == LIMIT
        assert [d.code for d in blocked.diagnostics] == ["LIMIT_EXCEEDED"]


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_parser_diagnostics_share_budget_with_adapter(kind: str):
    if kind == "tradition":
        text = "traditions = { bad ^ = 2 " + " ".join(
            f"tr_{i} = {{}}" for i in range(LIMIT + 100)
        ) + " }"
    else:
        text = "bad ^ = 2 " + " ".join(
            f"ascension_perk = {{ id = perk_{i} }}"
            for i in range(LIMIT + 100)
        )
    raw, ctx = text.encode(), context(kind, text.encode())
    parsed = parse_bytes(raw)
    assert any(d.code == "PARSE_UNKNOWN_SYNTAX" for d in parsed.diagnostics)
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        result = adapt_domain(parsed, raw, ctx, kind)
    assert result.blocked and not result.candidates
    assert make.call_count == LIMIT - len(parsed.diagnostics) - 1


@pytest.mark.parametrize("kind", KINDS)
def test_wave3_single_parse_per_file_vs_per_candidate_verification(kind: str):
    two = sample(kind, game_id="one") + "\n" + sample(kind, game_id="two")
    raw, ctx, result = adapted(kind, two)
    assert len(result.candidates) == 2
    with patch.object(domain, "parse_bytes", wraps=parse_bytes) as parse:
        actual = adapt_domain(parse_bytes(raw), raw, ctx, kind)
        assert len(actual.candidates) == 2
    assert parse.call_count == 1
    with patch.object(domain, "parse_bytes", wraps=parse_bytes) as parse:
        assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)
    assert parse.call_count == 2
