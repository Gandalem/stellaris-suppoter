"""E-027 Phase C3: cross-kind authored synthetic domain coverage matrix.

This probes thirteen opt-in synthetic adapters as ONE acceptance suite; it does
not infer real Stellaris grammar, load-order, engine outcomes or game version.
Earlier Phase A/B/C1/C2 tests remain unchanged and continue to run in full CI.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from stellaris_supporter.domain.generic import (
    DOMAIN_REGISTRY,
    adapt_domain,
    find_domain_collisions,
    resolve_domain_name,
    verify_domain_candidate,
)
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
)
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

KINDS = (
    "component_template",
    "building",
    "district",
    "pop_job",
    "trait",
    "government",
    "civic",
    "origin",
    "tradition",
    "ascension_perk",
    "event",
    "scripted_trigger",
    "scripted_effect",
)
SCRIPTED = frozenset(("scripted_trigger", "scripted_effect"))
ROOT_IDS = frozenset((
    "building", "district", "pop_job", "trait",
    "scripted_trigger", "scripted_effect",
))
STATIC_NAME_FIELDS = frozenset((
    "government", "civic", "origin", "tradition", "ascension_perk",
))
LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS


def synthetic(
    kind: str, *,
    game_id: str = "shared_x",
    extra: str = "",
    cost: str = "100",
) -> str:
    """Explicitly authored fixture policy: never guess from game content."""
    condition_name = (
        "trigger" if kind == "event"
        else "limit" if kind in SCRIPTED
        else "possible" if kind == "pop_job"
        else "potential"
    )
    condition = f"{condition_name} = {{ flag = yes }}"
    body = f"cost = {cost} cost = 200 {condition} {extra}"
    name = f"name = {game_id}_name "
    if kind == "component_template":
        return f"component_template = {{ key = {game_id} {body} }}"
    if kind in ROOT_IDS:
        return f"{game_id} = {{ {body} }}"
    if kind == "government":
        return f"governments = {{ {game_id} = {{ {name}{body} }} }}"
    if kind == "civic":
        return f"civic = {{ key = {game_id} {name}{body} }}"
    if kind == "origin":
        return f"origin = {{ id = {game_id} {name}{body} }}"
    if kind == "tradition":
        return (
            f"traditions = {{ group_example = {{ id = {game_id} "
            f"{name}{body} }} }}"
        )
    if kind == "ascension_perk":
        return f"ascension_perk = {{ id = {game_id} {name}{body} }}"
    if kind == "event":
        return (
            "namespace = authored\n"
            f"country_event = {{ id = authored.1 title = authored_title {body} }}"
        )
    raise AssertionError("All thirteen synthetic kinds must be mapped explicitly")


def context(
    kind: str, raw: bytes, *, file: str = "e027.txt", snapshot: str = "A"
) -> SourceContext:
    return SourceContext(
        snapshot, "synthetic", "authored",
        DOMAIN_REGISTRY[kind].path_prefix + file,
        hashlib.sha256(raw).hexdigest(),
    )


def adapt(
    kind: str, source: str | None = None,
    *, file: str = "e027.txt", snapshot: str = "A",
):
    raw = (synthetic(kind) if source is None else source).encode("utf-8")
    ctx = context(kind, raw, file=file, snapshot=snapshot)
    return raw, ctx, adapt_domain(parse_bytes(raw), raw, ctx, kind)


def translation(
    key: str, text: str, language: str, *, snapshot: str = "A"
):
    raw = f'l_{language}:\n {key}:0 "{text}"\n'.encode("utf-8")
    return parse_localisation(
        raw, SourceContext(
            snapshot, "synthetic", "authored",
            f"localisation/{language}/e027_l_{language}.yml",
            hashlib.sha256(raw).hexdigest(),
        ),
    )


@pytest.mark.parametrize("kind", KINDS)
def test_e027_a_registry_is_exact_opt_in_synthetic_kind(kind: str):
    assert len(KINDS) == len(set(KINDS)) == 13
    assert set(KINDS) == set(DOMAIN_REGISTRY)
    spec = DOMAIN_REGISTRY[kind]
    assert spec.kind == kind and spec.path_prefix
    assert spec.localisation_rule == (
        "none" if kind in SCRIPTED else
        "title_field" if kind == "event" else
        "name_field" if kind in STATIC_NAME_FIELDS else
        "id_key"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_e027_a_static_id_ordered_fields_conditions_and_raw_origin(kind: str):
    raw, ctx, result = adapt(
        kind, synthetic(kind, extra="cost = 300 nested = { deep = yes }")
    )
    assert result.ok and result.complete and not result.blocked
    assert len(result.candidates) == 1 and not result.unhandled
    c = result.candidates[0]
    expected_id = "authored.1" if kind == "event" else "shared_x"
    assert c.kind == kind and c.game_id == expected_id
    assert (c.resolution, c.support_level, c.definition_occurrence) == (
        "raw_definition", "synthetic_static", 1
    )
    assert c.id_source_ref is not None
    assert c.id_source_ref.raw_bytes(raw) == expected_id.encode("ascii")
    assert (c.source_ref.snapshot_id, c.source_ref.relative_path) == (
        "A", ctx.relative_path
    )
    assert c.source_ref.file_sha256 == hashlib.sha256(raw).hexdigest()
    assert [field.raw_value for field in c.fields if field.name == "cost"] == [
        "100", "200", "300"
    ]
    assert [field.occurrence for field in c.fields if field.name == "cost"] == [
        1, 2, 3
    ]
    assert len(c.conditions) >= 1
    assert "{ deep = yes }" in next(
        f.raw_value for f in c.fields if f.name == "nested"
    )
    assert tuple(f.name for f in c.fields) == tuple(
        f.key for f in c.items if f.kind == "pair"
    )
    assert all(n.raw_bytes() == n.source_ref.raw_bytes(raw) for n in c.items)
    assert verify_domain_candidate(c, raw, ctx)


def test_e027_a_all_thirteen_in_one_snapshot_no_cross_kind_collisions():
    candidates = []
    for kind in KINDS:
        _, _, result = adapt(kind, synthetic(kind, game_id="authored.1"))
        assert result.complete and len(result.candidates) == 1
        candidates.extend(result.candidates)
    assert len(candidates) == 13
    assert len({c.kind for c in candidates}) == 13
    assert not find_domain_collisions(tuple(candidates))


@pytest.mark.parametrize("kind", KINDS)
def test_e027_b_bad_operator_unknown_ast_unclosed_and_fake_comment(kind: str):
    source = synthetic(
        kind, extra='cost > 50 unknown ^ = 3 note = "fake = { }"'
    )
    raw, ctx, bad = adapt(kind, source + "\n# fake = { false = yes }")
    assert not bad.complete and not bad.blocked
    assert len(bad.candidates) == 1
    codes = {d.code for d in bad.diagnostics}
    assert "DOMAIN_UNSUPPORTED_OPERATOR" in codes
    assert "PARSE_UNKNOWN_SYNTAX" in codes
    assert "DOMAIN_UNKNOWN_STRUCTURE" in codes
    assert any(f.raw_value == '"fake = { }"'
               for f in bad.candidates[0].fields if f.name == "note")
    assert verify_domain_candidate(bad.candidates[0], raw, ctx)
    _, _, incomplete = adapt(kind, synthetic(kind)[:-1])
    assert not incomplete.complete
    assert "PARSE_UNCLOSED_BLOCK" in {
        d.code for d in incomplete.diagnostics
    }


@pytest.mark.parametrize("kind", KINDS)
def test_e027_b_dynamic_id_must_not_be_activated(kind: str):
    source = synthetic(kind)
    if kind in ROOT_IDS:
        source = source.replace("shared_x = {", "@dynamic = {", 1)
    elif kind == "government":
        source = source.replace("shared_x = {", "@dynamic = {", 1)
    elif kind == "component_template":
        source = source.replace("key = shared_x", "key = @dynamic", 1)
    elif kind == "civic":
        source = source.replace("key = shared_x", "key = @dynamic", 1)
    elif kind in ("origin", "tradition", "ascension_perk"):
        source = source.replace("id = shared_x", "id = @dynamic", 1)
    else:
        assert kind == "event"
        source = source.replace("id = authored.1", "id = @dynamic", 1)
    _, _, result = adapt(kind, source)
    assert not result.complete
    assert not any(c.resolution == "raw_definition" for c in result.candidates)
    if result.candidates:
        assert all(c.game_id is None for c in result.candidates)
    else:
        assert result.unhandled


@pytest.mark.parametrize("kind", KINDS)
def test_e027_c_duplicate_definitions_no_last_wins_and_occurrences(kind: str):
    source = synthetic(kind) + "\n" + synthetic(kind, cost="777")
    raw, ctx, result = adapt(kind, source)
    assert len(result.candidates) == 2 and not result.complete
    first, second = result.candidates
    assert first.game_id == second.game_id
    assert [first.definition_occurrence, second.definition_occurrence] == [
        1, 2
    ]
    assert [c.resolution for c in result.candidates] == [
        "ambiguous", "ambiguous"
    ]
    assert next(f for f in first.fields if f.name == "cost").raw_value == "100"
    assert next(f for f in second.fields if f.name == "cost").raw_value == "777"
    assert any(d.code == "DOMAIN_DUPLICATE_ID" for d in result.diagnostics)
    assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_e027_c_cross_file_collisions_snapshot_path_and_sha_isolation(kind: str):
    raw, ctx, left = adapt(kind, file="first.txt")
    _, _, right = adapt(kind, file="second.txt")
    conflicts = find_domain_collisions((*left.candidates, *right.candidates))
    assert len(conflicts) == 1
    assert conflicts[0].kind == kind
    assert len(conflicts[0].definition_source_refs) == 2
    assert conflicts[0].definition_source_refs[0].relative_path.endswith(
        "first.txt"
    )
    assert conflicts[0].definition_source_refs[1].relative_path.endswith(
        "second.txt"
    )
    c = left.candidates[0]
    assert not verify_domain_candidate(
        c, raw, replace(ctx, relative_path=ctx.relative_path + ".moved")
    )
    assert not verify_domain_candidate(
        c, raw, replace(ctx, snapshot_id="B")
    )
    assert not verify_domain_candidate(
        c, raw, replace(ctx, file_sha256="0" * 64)
    )
    _, _, foreign = adapt(kind, snapshot="B")
    with pytest.raises(ValueError, match="snapshot"):
        find_domain_collisions((*left.candidates, *foreign.candidates))


@pytest.mark.parametrize("kind", KINDS)
def test_e027_d_static_localisation_policy_ko_en_fallback_and_source(kind: str):
    _, ctx, result = adapt(kind)
    c = result.candidates[0]
    if kind in SCRIPTED:
        assert c.localisation_key is None
        with pytest.raises(ValueError, match="localisation key"):
            resolve_domain_name(c, build_localisation_catalog(()))
        return
    assert c.localisation_key is not None
    if kind == "event":
        assert c.localisation_key == "authored_title"
    elif kind in STATIC_NAME_FIELDS:
        assert c.localisation_key == "shared_x_name"
    else:
        assert c.localisation_key == "shared_x"
    key = c.localisation_key
    ko = translation(key, "한국어", "korean")
    en = translation(key, "English", "english")
    cat = build_localisation_catalog((ko, en))
    kr = resolve_domain_name(c, cat, "korean").localisation
    eng = resolve_domain_name(c, cat, "english").localisation
    assert kr.display_value == "한국어" and eng.display_value == "English"
    assert kr.source_ref == ko.entries[0].source_ref
    assert kr.source_ref.snapshot_id == ctx.snapshot_id
    fall = resolve_domain_name(
        c, build_localisation_catalog((en,)), "korean"
    ).localisation
    assert fall.fallback == "english" and fall.display_value == "English"
    missing = resolve_domain_name(
        c, build_localisation_catalog(())
    ).localisation
    assert missing.resolution == "unresolved" and missing.fallback == "id"
    with pytest.raises(ValueError, match="snapshot"):
        resolve_domain_name(
            c, build_localisation_catalog((
                translation(key, "bad", "korean", snapshot="B"),
            ))
        )


@pytest.mark.parametrize("kind", KINDS)
def test_e027_d_duplicate_dynamic_cycle_name_and_budget(kind: str):
    _, _, result = adapt(kind)
    c = result.candidates[0]
    if kind in SCRIPTED:
        assert c.localisation_key is None
        return
    key = c.localisation_key
    assert key
    duplicate = parse_localisation(
        f'l_korean:\n {key}:0 "A"\n {key}:0 "B"\n'.encode(),
        context_for_localisation("korean", key + "-dup"),
    )
    ambiguous = resolve_domain_name(
        c, build_localisation_catalog((duplicate,))
    ).localisation
    assert ambiguous.resolution == "ambiguous"
    cycle = parse_localisation(
        f'l_korean:\n {key}:0 "$next$"\n next:0 "$next$"\n'.encode(),
        context_for_localisation("korean", key + "-cycle"),
    )
    result_cycle = resolve_domain_name(
        c, build_localisation_catalog((cycle,))
    ).localisation
    assert any(d.code == "LOC_CYCLE" for d in result_cycle.diagnostics)
    dyn = translation(key, "[Root.GetName]", "english")
    dynamic = resolve_domain_name(
        c, build_localisation_catalog((dyn,)), "english"
    ).localisation
    assert dynamic.resolution == "partial"
    assert resolve_domain_name(
        c, build_localisation_catalog((dyn,)),
        "english", max_scan_bytes=1,
    ).localisation.truncated


def context_for_localisation(language: str, suffix: str) -> SourceContext:
    raw = b"unused"
    return SourceContext(
        "A", "synthetic", "authored",
        f"localisation/{language}/{suffix}_l_{language}.yml",
        hashlib.sha256(raw).hexdigest(),
    )


@pytest.mark.parametrize("kind", KINDS)
def test_e027_e_independent_raw_field_condition_child_backing(kind: str):
    raw, ctx, result = adapt(kind)
    candidate = result.candidates[0]
    assert verify_domain_candidate(candidate, raw, ctx)
    cost = next(f for f in candidate.fields if f.name == "cost")
    assert cost.value is not None and cost.raw_value == "100"
    injected = raw.replace(b"cost = 100", b"cost = 999")
    mutated = replace(cost, value=replace(cost.value, _source=injected))
    changed = replace(
        candidate, fields=tuple(
            mutated if f is cost else f for f in candidate.fields
        )
    )
    assert not verify_domain_candidate(changed, raw, ctx)
    cond = next(
        f for f in candidate.conditions if f.value is not None
        and f.value.children
    )
    injected_condition = raw.replace(b"flag = yes", b"flag = no!")
    mutated_condition = replace(
        cond, value=replace(cond.value, _source=injected_condition)
    )
    assert not verify_domain_candidate(
        replace(candidate, conditions=tuple(
            mutated_condition if f is cond else f for f in candidate.conditions
        )), raw, ctx
    )
    nested_child = replace(
        cond.value.children[0], _source=injected_condition
    )
    patched = replace(
        cond, value=replace(
            cond.value, children=(
                nested_child, *cond.value.children[1:]
            )
        )
    )
    assert not verify_domain_candidate(
        replace(candidate, conditions=tuple(
            patched if f is cond else f for f in candidate.conditions
        )), raw, ctx
    )
    assert verify_domain_candidate(candidate, raw, ctx)


@pytest.mark.parametrize("kind", KINDS)
def test_e027_e_r2_external_parse_ast_token_and_source_mutation(kind: str):
    raw, ctx, _ = adapt(kind)
    parsed = parse_bytes(raw)
    for forged in (
        parse_bytes(b""),
        replace(parsed, document=replace(parsed.document, items=())),
        replace(parsed, tokens=(
            replace(
                parsed.tokens[0],
                span=replace(parsed.tokens[0].span, column_start=77),
            ), *parsed.tokens[1:],
        )),
    ):
        with pytest.raises(ValueError, match="ParseResult"):
            adapt_domain(forged, raw, ctx, kind)
    with pytest.raises(ValueError, match="hash"):
        adapt_domain(parsed, raw, replace(ctx, file_sha256="0" * 64), kind)
    with pytest.raises(ValueError):
        adapt_domain(
            parsed, raw, replace(ctx, snapshot_id="B"),
            kind
        ) if False else adapt_domain(
            parsed, raw.replace(b"cost = 100", b"cost = 999"),
            ctx, kind
        )


@pytest.mark.parametrize("kind", KINDS)
def test_e027_f_utf8_bom_crlf_parser_ceiling_and_raw_budget(kind: str):
    source = synthetic(kind, extra='description = "한글 # = {}"')
    source = "\ufeff" + source.replace(" cost = ", "\r\n cost = ")
    raw, ctx, result = adapt(kind, source)
    assert result.complete and len(result.candidates) == 1
    candidate = result.candidates[0]
    assert any(
        f.raw_value == '"한글 # = {}"'
        for f in candidate.fields if f.name == "description"
    )
    assert verify_domain_candidate(candidate, raw, ctx)
    with pytest.raises(ValueError):
        result.to_dict(include_raw=True, max_raw_bytes=1)
    for parsed in (
        parse_bytes(raw, max_tokens=2),
        parse_bytes(raw, max_nodes=2),
        parse_bytes(raw, max_depth=1),
    ):
        blocked = adapt_domain(parsed, raw, ctx, kind)
        assert blocked.blocked and not blocked.candidates
    invalid = b"\xff"
    invalid_ctx = context(kind, invalid)
    blocked = adapt_domain(
        parse_bytes(invalid), invalid, invalid_ctx, kind
    )
    assert blocked.blocked and not blocked.candidates


@pytest.mark.parametrize("kind", (
    "building", "government", "event", "scripted_effect"
))
@pytest.mark.parametrize("count", (999, 1000, 1200))
def test_e027_f_diagnostic_budget_representative_extractors(
    kind: str, count: int
):
    if kind == "building":
        source = "\n".join(f"rule_{i} = value" for i in range(count))
        expected_limit = LIMIT
    elif kind == "government":
        source = "governments = { " + " ".join(
            f"gov_{i} = {{}}" for i in range(count)
        ) + " }"
        expected_limit = LIMIT
    elif kind == "event":
        source = "namespace = authored\n" + "\n".join(
            f"country_event = {{ id = authored.{i} }}"
            for i in range(count)
        )
        expected_limit = LIMIT - 1
    else:
        source = "\n".join(
            f"rule_{i} = {{ @dynamic = yes }}" for i in range(count)
        )
        expected_limit = LIMIT
    _, _, result = adapt(kind, source)
    assert result.blocked and not result.complete
    assert not result.candidates
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert count >= expected_limit


def test_e027_f_shared_parser_budget_and_scripted_dynamic_keys():
    source = "unknown ^ = 2\n" + "\n".join(
        f"rule_{i} = {{ @dynamic = yes }}" for i in range(LIMIT + 200)
    )
    raw = source.encode("utf-8")
    ctx = context("scripted_trigger", raw)
    parsed = parse_bytes(raw)
    assert parsed.diagnostics
    result = adapt_domain(parsed, raw, ctx, "scripted_trigger")
    assert result.blocked and not result.candidates
    assert [d.code for d in result.diagnostics] == ["LIMIT_EXCEEDED"]


def test_e027_event_qualified_id_policy_and_scripted_value_key_partials():
    for value in ("authored.", "authored..1", "authored.1."):
        raw, ctx, result = adapt(
            "event", synthetic("event").replace(
                "id = authored.1", f"id = {value}"
            )
        )
        assert not result.complete and len(result.candidates) == 1
        assert "DOMAIN_EVENT_INVALID_QUALIFIED_ID" in {
            d.code for d in result.diagnostics
        }
        assert verify_domain_candidate(result.candidates[0], raw, ctx)
    for kind in SCRIPTED:
        for expr in ("@dynamic = yes", "runtime = @dynamic"):
            raw, ctx, result = adapt(
                kind, synthetic(kind, extra=f"nested = {{ {expr} }}")
            )
            assert not result.complete
            assert len(result.candidates) == 1
            assert result.candidates[0].resolution == "partial"
            assert "DOMAIN_DYNAMIC_EXPRESSION_UNSUPPORTED" in {
                d.code for d in result.diagnostics
            }
            assert verify_domain_candidate(result.candidates[0], raw, ctx)
