"""E-020–E-022: synthetic-only deterministic retrieval, literals and isolation."""

from __future__ import annotations

import hashlib
import sqlite3
import unicodedata
from pathlib import Path

import pytest

from stellaris_supporter.domain import SourceContext, SourceRef, adapt_technologies
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.retrieval import Query, SearchService, VerifiedAlias
from stellaris_supporter.storage import (
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    snapshot_identity,
)

POLICY = SnapshotPolicy("parser-1", "adapter-1", "a" * 64)


def _build(
    repo: SnapshotRepository,
    *,
    source_text: str = "demo_alloy = { cost = 0 }\n",
    korean: str = "합금 연구",
    english: str = "Alloy Research",
    extra_technology: str = "",
    activate: bool = True,
) -> str:
    sources = (
        SourceFileInput(
            "synthetic", "demo", "common/technology/demo.txt",
            (source_text + extra_technology).encode(),
        ),
        SourceFileInput(
            "synthetic", "demo", "localisation/korean/demo.yml",
            ('l_korean:\n demo_alloy:0 "' + korean + '"\n').encode(),
        ),
        SourceFileInput(
            "synthetic", "demo", "localisation/english/demo.yml",
            ('l_english:\n demo_alloy:0 "' + english + '"\n').encode(),
        ),
    )
    sid = snapshot_identity(sources, POLICY).snapshot_id

    def ctx(src):
        return SourceContext(
            sid, src.source_kind, src.source_id, src.relative_path,
            hashlib.sha256(src.data).hexdigest(),
        )

    adapted = adapt_technologies(parse_bytes(sources[0].data), sources[0].data, ctx(sources[0]))
    assert adapted.complete
    docs = tuple(parse_localisation(src.data, ctx(src)) for src in sources[1:])
    assert all(d.complete for d in docs)
    catalog = build_localisation_catalog(docs)
    names = tuple(resolve_technology_name(c, catalog) for c in adapted.candidates)
    repo.stage(
        sources, POLICY, candidates=adapted.candidates,
        entries=tuple(entry for doc in docs for entry in doc.entries),
        localised_names=names,
    )
    if activate:
        repo.activate(sid, allow_partial=True)
    return sid


def test_e020_exact_korean_english_and_id_priority(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    sid = _build(repo)
    with_service = SearchService(repo)
    for query, language, reason in [
        ("demo_alloy", "korean", "game_id_exact"),
        ("합금 연구", "korean", "name_exact"),
        ("ALLOY RESEARCH", "english", "name_exact"),
        ("합금", "korean", "name_prefix"),
        ("연구", "korean", "name_substring"),
    ]:
        result = with_service.search(Query(query, language=language))
        assert result.context is not None and result.context.snapshot_id == sid
        assert result.results and result.results[0].match_reason == reason, result
        assert result.results[0].game_id == "demo_alloy"
        assert result.results[0].definition_source_ref.snapshot_id == sid
        assert result.status in {"ok", "partial"}
    with_service.close()


def test_e020_explicit_verified_alias_and_source_ref(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    sid = _build(repo, korean="합금 별칭")
    entity = repo.entities()[0]
    loc = repo.localisation_entries()
    target = next(x for x in loc if x["language"] == "korean")
    ref = SourceRef(**target["value_source_ref"])
    alias = VerifiedAlias(sid, entity["entity_key"], "별칭", ref)
    service = SearchService(repo, aliases=(alias,))
    result = service.search(Query("별칭"))
    assert result.results[0].match_reason == "alias_exact"
    assert result.results[0].match_source_ref == ref
    service.close()


def test_e021_normalization_and_no_fts_parity(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _build(repo, korean="합금  연구", english="CaseFold Alloy")
    for enable in (True, False):
        service = SearchService(repo, enable_fts=enable)
        for term, lang in [
            ("합금 연구", "korean"),
            (unicodedata.normalize("NFD", "합금 연구"), "korean"),
            ("CASEFOLD ALLOY", "english"),
            ("합금", "korean"),
        ]:
            result = service.search(Query(term, language=lang))
            assert result.results and result.results[0].game_id == "demo_alloy"
        service.close()


@pytest.mark.parametrize("text", [
    "'", '"', "()", "*", "AND", "OR", "NOT", "%", "_", "\\",
    "demo_alloy' OR 1=1 --", '"" OR (', "「", "-",
])
def test_e022_metacharacters_are_literal_and_safe(tmp_path: Path, text: str) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _build(repo)
    result = SearchService(repo).search(Query(text))
    assert result.status in {"not_found", "partial", "ok"}
    assert result.context is not None
    assert all(x.snapshot_id == result.context.snapshot_id for x in result.results)


@pytest.mark.parametrize("query", [
    Query(""), Query(" "), Query("x" * 513), Query("x", limit=0),
    Query("x", limit=101), Query("x", kind="event"),
    Query("x", language="spanish"), Query("x", snapshot_id="nope"),
])
def test_e022_invalid_queries_have_distinct_diagnostic(tmp_path: Path, query: Query) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    response = SearchService(repo).search(query)
    assert response.status == "error"
    assert response.diagnostics[0].code == "QUERY_INVALID"


def test_e022_no_active_and_unready_snapshot(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    service = SearchService(repo)
    assert service.search(Query("demo_alloy")).diagnostics[0].code == "SNAPSHOT_NOT_READY"
    sid = _build(repo, activate=False)
    assert service.search(Query("demo_alloy", snapshot_id=sid)).results
    service.close()


def test_e020_duplicate_id_kept_and_stably_ordered(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _build(repo, extra_technology="demo_alloy = { cost = 1 }\n")
    service = SearchService(repo)
    result = service.search(Query("demo_alloy"))
    assert len(result.results) == 2
    assert all(r.resolution == "ambiguous" for r in result.results)
    assert len({r.entity_key for r in result.results}) == 2
    assert result.results == service.search(Query("demo_alloy")).results
    service.close()


def test_e020_snapshot_pinning_and_active_switch(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    first = _build(repo, korean="이전 이름")
    second = _build(repo, korean="새로운 이름")
    service = SearchService(repo)
    a = service.search(Query("이전 이름", snapshot_id=first))
    b = service.search(Query("새로운 이름", snapshot_id=second))
    assert a.results and a.context.snapshot_id == first
    assert b.results and b.context.snapshot_id == second
    assert not service.search(Query("이전 이름")).results
    repo.activate(first, allow_partial=True)
    assert service.search(Query("이전 이름")).results
    service.close()


def test_e022_limit_and_not_found(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _build(
        repo, extra_technology="".join(
            f"demo_{i:03d} = {{ cost = 0 }}\n" for i in range(30)
        ),
    )
    service = SearchService(repo)
    response = service.search(Query("demo", limit=2))
    # Only verified names participate in prefix ranking; missing IDs are not
    # promoted to synthetic names.
    assert len(response.results) <= 2
    assert service.search(Query("nothing-ever")).status in {"not_found", "partial"}
    service.close()


def test_e022_cache_integrity_failure_is_error_not_stale_quote(tmp_path: Path) -> None:
    repo = SnapshotRepository(tmp_path / "db")
    _build(repo)
    service = SearchService(repo)
    assert service.search(Query("demo_alloy")).results
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("UPDATE source_files SET cache_sha256=? WHERE relative_path LIKE '%technology%'",
                     ("b" * 64,))
    failed = service.search(Query("demo_alloy"))
    assert failed.status == "error"
    assert failed.diagnostics[0].code == "SOURCE_CHANGED"
    service.close()
