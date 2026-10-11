"""TASK-012 E-023/E-024/E-025: only authored synthetic snapshot fixtures."""
from __future__ import annotations

import hashlib
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
