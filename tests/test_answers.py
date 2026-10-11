"""TASK-012 E-023/E-024/E-025: only authored synthetic snapshot fixtures."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from stellaris_supporter.answers import AnswerService
from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import (
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    snapshot_identity,
)


def staged(
    repo: SnapshotRepository,
    *,
    cost: str = "@demo_cost",
    korean: str = "합금 $demo_suffix$",
    suffix: str = "연구",
    language: str = "korean",
    branch: str = "unknown",
    version: str | None = None,
    activate: bool = True,
    tech_extra: str = "",
    english_suffix: bool = False,
) -> str:
    script = (
        "\ufeffdemo_alloy = {\r\n"
        f"    cost = {cost}\r\n"
        "    tier = 2\r\n"
        "    category = physics\r\n"
        "}\r\n" + tech_extra
    ).encode("utf-8")
    korean_loc = ('l_korean:\n demo_alloy:0 "' + korean + '"\n' +
                  ("" if english_suffix else ' demo_suffix:0 "' + suffix + '"\n')).encode()
    english_loc = ('l_english:\n demo_alloy:0 "Alloy Research"\n' +
                   (' demo_suffix:0 "' + suffix + '"\n' if english_suffix else '')).encode()
    sources = (
        SourceFileInput("synthetic", "demo", "common/technology/demo.txt", script),
        SourceFileInput("synthetic", "demo", "localisation/korean/demo.yml", korean_loc),
        SourceFileInput("synthetic", "demo", "localisation/english/demo.yml", english_loc),
    )
    policy = SnapshotPolicy(
        "parser-1", "adapter-1", "a" * 64,
        branch=branch, game_version=version,
        game_version_source="metadata" if version else "unknown",
    )
    sid = snapshot_identity(sources, policy).snapshot_id

    def context(source: SourceFileInput) -> SourceContext:
        return SourceContext(sid, source.source_kind, source.source_id,
                             source.relative_path, hashlib.sha256(source.data).hexdigest())

    adapted = adapt_technologies(parse_bytes(script), script, context(sources[0]))
    documents = tuple(parse_localisation(s.data, context(s)) for s in sources[1:])
    names = tuple(resolve_technology_name(c, build_localisation_catalog(documents))
                  for c in adapted.candidates)
    repo.stage(
        sources, policy, candidates=adapted.candidates,
        entries=tuple(e for doc in documents for e in doc.entries),
        localised_names=names,
    )
    if activate:
        repo.activate(sid, allow_partial=True)
    return sid


def service(repo: SnapshotRepository) -> AnswerService:
    return AnswerService(SearchService(repo), repo)


def test_e023_field_value_span_bom_crlf_exact(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    sid = staged(repo)
    result = service(repo).answer(Query("demo_alloy"))
    assert result.context and result.context.snapshot_id == sid
    assert result.results and result.status == "partial"
    hit = result.results[0]
    fields = {field.field_name: field for field in hit.facts}
    assert fields["cost"].raw_expression == "@demo_cost"
    assert fields["cost"].support_status == "unsupported_expression"
    assert fields["tier"].raw_expression == "2"
    assert fields["tier"].support_status == "literal"
    assert fields["category"].raw_expression == "physics"
    for field in hit.facts:
        assert field.source_ref.snapshot_id == sid
        assert field.value_source_ref is not None
        assert repo.citation_bytes(field.value_source_ref).decode("utf-8") == field.raw_expression
        assert field.field_name.encode() in repo.citation_bytes(field.source_ref)
        assert field.value_source_ref.line_start == 2 if field.field_name == "cost" else True
    assert hit.definition_source_ref.relative_path.startswith("common/")
    assert hit.localisation_source_ref is not None
    assert hit.localisation_source_ref.relative_path.startswith("localisation/")


def test_e023_nested_static_korean_and_english_reference_evidence(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo, korean="합금 $demo_suffix$", suffix="Research", english_suffix=True)
    hit = service(repo).answer(Query("합금 Research")).results[0]
    assert hit.display_name == "합금 Research"
    assert hit.localisation_source_ref is not None
    assert hit.localisation_source_ref.relative_path.endswith("korean/demo.yml")
    assert [x.language_used for x in hit.localisation_reference_selections] == ["english"]
    assert any(r.relative_path.endswith("english/demo.yml") for r in hit.source_refs)
    assert all(repo.citation_bytes(r) for r in hit.source_refs)


def test_e023_forged_line_and_utf8_offset_fail_closed(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    hit = service(repo).answer(Query("demo_alloy")).results[0]
    ref = next(f.value_source_ref for f in hit.facts if f.field_name == "cost")
    assert ref is not None
    with pytest.raises(Exception):
        repo.citation_bytes(replace(ref, line_start=999))
    with pytest.raises(Exception):
        repo.citation_bytes(replace(ref, byte_end=ref.byte_end + 10000))


def test_e023_cache_pointer_tampering_returns_error(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    svc = service(repo)
    assert svc.answer(Query("demo_alloy")).results
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("UPDATE source_files SET cache_sha256=? WHERE relative_path LIKE '%technology%'",
                     ("b" * 64,))
    answer = svc.answer(Query("demo_alloy"))
    assert answer.status == "error"
    assert not answer.results


@pytest.mark.parametrize("question", [
    "연구 등장 확률", "전투 승률", "실제 연구 완료 시간", "모드 적용 이후 최종 효과",
    "연구 조건 참 평가", "probability", "combat win rate",
])
def test_e024_unsupported_calculations_abstain(tmp_path: Path, question: str) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    result = service(repo).answer(Query(question))
    assert result.status == "unsupported"
    assert not result.results
    assert result.diagnostics[0].code == "UNSUPPORTED_CALCULATION"


def test_e024_not_found_and_missing_field(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    svc = service(repo)
    assert svc.answer(Query("unknown_tech")).status == "not_found"
    response = svc.answer(Query("demo_alloy"), field="nonexistent")
    assert response.status == "partial"
    assert not response.results[0].facts
    assert any(d.code == "FIELD_NOT_FOUND" for d in response.results[0].warnings)


def test_e024_duplicate_definitions_not_merged(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo, tech_extra="demo_alloy = { tier = 9 }\n")
    answer = service(repo).answer(Query("demo_alloy"))
    assert answer.status == "partial"
    assert len(answer.results) == 2
    assert len({x.entity_key for x in answer.results}) == 2
    assert all(x.resolution == "ambiguous" for x in answer.results)
    assert any(d.code == "DUPLICATE_GAME_ID" for x in answer.results for d in x.warnings)


def test_e025_stable_beta_explicit_and_active_switch(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    stable = staged(repo, cost="100", korean="안정 연구", branch="stable", version="1.0")
    beta = staged(repo, cost="200", korean="시험 연구", branch="beta", version="1.1")
    svc = service(repo)
    def cost(sid: str) -> tuple[str | None, str]:
        answer = svc.answer(Query("demo_alloy", snapshot_id=sid))
        return next(x.raw_expression for x in answer.results[0].facts
                    if x.field_name == "cost"), answer.context.branch
    assert cost(stable) == ("100", "stable")
    assert cost(beta) == ("200", "beta")
    assert next(x.raw_expression for x in svc.answer(Query("demo_alloy")).results[0].facts
                if x.field_name == "cost") == "200"
    repo.activate(stable, allow_partial=True)
    assert next(x.raw_expression for x in svc.answer(Query("demo_alloy")).results[0].facts
                if x.field_name == "cost") == "100"
    assert cost(beta) == ("200", "beta")


def test_e025_switch_after_search_does_not_mix_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    stable = staged(repo, cost="100", korean="안정 연구", branch="stable")
    beta = staged(repo, cost="200", korean="시험 연구", branch="beta")
    repo.activate(stable, allow_partial=True)
    svc = service(repo)
    original = svc.search.search

    def change_active(query: Query):
        result = original(query)
        repo.activate(beta, allow_partial=True)
        return result

    monkeypatch.setattr(svc.search, "search", change_active)
    result = svc.answer(Query("demo_alloy"))
    assert result.context and result.context.snapshot_id == stable
    assert result.context.branch == "stable"
    assert result.results[0].snapshot_id == stable
    assert any(f.raw_expression == "100" for f in result.results[0].facts)
    assert all(r.snapshot_id == stable for r in result.results[0].source_refs)


def test_e025_unknown_version_remains_null(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    response = service(repo).answer(Query("demo_alloy"))
    assert response.context and response.context.game_version is None
    assert response.context.branch == "unknown"


def test_e023_corrupted_english_dependency_only_fails_closed(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo, korean="합금 $demo_suffix$", suffix="Research", english_suffix=True)
    svc = service(repo)
    assert svc.answer(Query("합금 Research")).results
    # The Korean root stays pristine; only the English referenced file is poisoned.
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute(
            "UPDATE source_files SET cache_sha256=? WHERE relative_path=?",
            ("b" * 64, "localisation/english/demo.yml"),
        )
    result = svc.answer(Query("합금 Research"))
    assert result.status == "error"
    assert not result.results
    assert result.diagnostics[0].code == "SOURCE_CHANGED"


def test_e025_forged_search_hit_cross_snapshot_ref_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    stable = staged(repo, cost="100", branch="stable")
    beta = staged(repo, cost="200", branch="beta")
    svc = service(repo)
    original = svc.search.search(Query("demo_alloy", snapshot_id=stable))
    assert original.results
    forged = replace(
        original.results[0],
        definition_source_ref=replace(original.results[0].definition_source_ref,
                                      snapshot_id=beta),
    )
    monkeypatch.setattr(svc.search, "search",
                        lambda query: replace(original, results=(forged,)))
    result = svc.answer(Query("demo_alloy", snapshot_id=stable))
    assert result.status == "error"
    assert result.results == ()
    assert result.diagnostics[0].code == "SOURCE_CHANGED"


def test_e024_invalid_non_string_query_is_typed_error(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    result = service(repo).answer(Query(None))  # type: ignore[arg-type]
    assert result.status == "error"
    assert result.results == ()
    assert result.diagnostics[0].code == "QUERY_INVALID"


def _synthetic_multi(
    repo: SnapshotRepository, scripts: tuple[tuple[str, str], ...],
    *, translations: tuple[tuple[str, str], ...] = (),
) -> str:
    src = tuple(
        SourceFileInput("synthetic", "demo", f"common/technology/{filename}", content.encode())
        for filename, content in scripts
    )
    loc = "l_english:\n" + "".join(
        f' {key}:0 "{value}"\n' for key, value in translations
    )
    src += (SourceFileInput("synthetic", "demo", "localisation/english/names.yml",
                            loc.encode()),)
    policy = SnapshotPolicy("parser-1", "adapter-1", "a" * 64)
    sid = snapshot_identity(src, policy).snapshot_id

    def ctx(x: SourceFileInput) -> SourceContext:
        return SourceContext(
            sid, x.source_kind, x.source_id, x.relative_path,
            hashlib.sha256(x.data).hexdigest(),
        )

    adapted = tuple(
        c for f in src[:-1]
        for c in adapt_technologies(parse_bytes(f.data), f.data, ctx(f)).candidates
    )
    doc = parse_localisation(src[-1].data, ctx(src[-1]))
    cat = build_localisation_catalog((doc,))
    repo.stage(
        src, policy, candidates=adapted, entries=doc.entries,
        localised_names=tuple(resolve_technology_name(c, cat) for c in adapted),
    )
    repo.activate(sid, allow_partial=True)
    return sid


def _mutate_candidate(repo: SnapshotRepository, entity: str, transform) -> None:
    with sqlite3.connect(repo.db_path) as conn:
        row = conn.execute(
            "SELECT candidate_json FROM entities WHERE game_id=?", (entity,)
        ).fetchone()
        assert row
        candidate = json.loads(row[0])
        transform(candidate)
        conn.execute(
            "UPDATE entities SET candidate_json=? WHERE game_id=?",
            (json.dumps(candidate, ensure_ascii=False), entity),
        )


def test_r1_cross_file_valid_refs_cannot_be_borrowed(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _synthetic_multi(repo, (
        ("a.txt", "demo_a = {\n cost = 100\n}\n"),
        ("b.txt", "demo_b = {\n cost = 999\n}\n"),
    ))
    b = repo.entities()[1]["candidate"]["fields"][0]
    # Preserve A's definition and valid caches, forge only child provenance.
    _mutate_candidate(repo, "demo_a", lambda c: c["fields"][0].update(
        source_ref=b["source_ref"], value_source_ref=b["value_source_ref"]
    ))
    answer = service(repo).answer(Query("demo_a"))
    assert answer.status == "error" and not answer.results
    assert answer.diagnostics[0].code == "SOURCE_CHANGED"
    assert next(f.raw_expression for f in service(repo).answer(
        Query("demo_b")).results[0].facts) == "999"


@pytest.mark.parametrize("mutation", ["name", "operator", "occurrence", "span", "value"])
def test_r2_forged_field_structure_rejected(tmp_path: Path, mutation: str) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _synthetic_multi(repo, ((
        "tech.txt",
        'demo_a = { cost = 100 cost_modifier = 999 cost = 200 '
        'note = "cost = 444" nested = { cost = 777 } }\n',
    ),))
    def alter(c):
        fields = c["fields"]
        if mutation == "name":
            fields[0]["source_ref"] = fields[1]["source_ref"]
            fields[0]["value_source_ref"] = fields[1]["value_source_ref"]
        elif mutation == "operator":
            fields[0]["operator"] = ">"
        elif mutation == "occurrence":
            fields[2]["occurrence"] = 1
        elif mutation == "span":
            fields[0]["source_ref"] = fields[3]["source_ref"]
        else:
            fields[0]["value_source_ref"] = fields[4]["value_source_ref"]
    _mutate_candidate(repo, "demo_a", alter)
    result = service(repo).answer(Query("demo_a"))
    assert result.status == "error" and result.results == ()
    assert result.diagnostics[0].code == "SOURCE_CHANGED"


def test_r2_normal_duplicate_nested_fields_preserved(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _synthetic_multi(repo, ((
        "tech.txt",
        'demo_a = { cost = 100 cost_modifier = 999 cost = 200 '
        'note = "cost = 444" nested = { cost = 777 } }\n',
    ),))
    result = service(repo).answer(Query("demo_a"))
    assert result.results
    assert [(f.field_name, f.occurrence) for f in result.results[0].facts] == [
        ("cost", 1), ("cost_modifier", 1), ("cost", 2), ("note", 1), ("nested", 1),
    ]


@pytest.mark.parametrize("name", ["Combat Computers", "Chance Discovery"])
def test_r3_normal_combat_chance_exact_names(tmp_path: Path, name: str) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _synthetic_multi(repo, (("tech.txt", "demo_a = { cost = 20 }\n"),),
                     translations=(("demo_a", name),))
    result = service(repo).answer(Query(name, language="english"))
    assert result.status == "ok"
    assert result.results[0].display_name == name
    assert result.results[0].match_reason == "name_exact"
    assert result.results[0].match_source_ref == result.results[0].localisation_source_ref


@pytest.mark.parametrize("query", [
    Query("combat", limit=0),
    Query("chance", kind="invalid"),
    Query("probability", snapshot_id="not-a-sha"),
])
def test_r3_bad_query_precedes_unsupported(tmp_path: Path, query: Query) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    staged(repo)
    result = service(repo).answer(query)
    assert result.status == "error" and result.diagnostics[0].code == "QUERY_INVALID"


def test_r4_request_global_fact_limit_and_cache_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    technology = "".join(
        f"demo_{i:03d} = {{ cost = {i} tier = 2 }}\n" for i in range(100)
    )
    _synthetic_multi(repo, (("tech.txt", technology),),
                     translations=tuple((f"demo_{i:03d}", "Demo Technology")
                                        for i in range(100)))
    original = repo.cache.read
    reads = []
    def tracked(digest, size):
        reads.append((digest, size))
        return original(digest, size)
    monkeypatch.setattr(repo.cache, "read", tracked)
    result = service(repo).answer(Query("Demo Technology", language="english", limit=100))
    assert result.status == "partial" and result.truncated
    assert sum(len(hit.facts) for hit in result.results) <= 64
    assert all(len(hit.source_refs) <= 256 for hit in result.results)
    # One search provenance check + one answer reader verification, never per citation.
    assert sum(1 for digest, _ in reads if digest == hashlib.sha256(
        technology.encode()).hexdigest()) == 2
    assert service(repo).answer(Query("demo_001")).results


def test_r4_exact_value_512_bytes_and_one_over(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _synthetic_multi(repo, (("a.txt", "demo_a = { note = " + "x" * 512 + " }\n"),))
    yes = service(repo).answer(Query("demo_a"))
    assert any(len(f.raw_expression.encode()) == 512 for f in yes.results[0].facts)
    repo2 = SnapshotRepository(tmp_path / "db2")
    _synthetic_multi(repo2, (("a.txt", "demo_a = { note = " + "x" * 513 + " }\n"),))
    no = service(repo2).answer(Query("demo_a"))
    assert no.status == "partial" and no.truncated
    assert not no.results[0].facts
