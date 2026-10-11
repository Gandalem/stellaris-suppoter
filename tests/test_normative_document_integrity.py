"""Guard normative Markdown contracts against duplicate insertion and broken inline code.

A well-linked document can still have repeated or truncated normative prose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"

HEADING_CONTRACTS = {
    "DATA_CONTRACTS.md": (
        "# 데이터 계약 v1",
        "## 출처",
        "## 스냅샷",
        "## AST·진단",
        "## 엔티티·관계·현지화",
        "## 질의·답변",
        "## 저장 구조",
    ),
    "PARSING.md": (
        "# 정적 파싱·현지화",
        "## 데이터 경로 조사 후보",
        "## lexer·AST",
        "## 도메인 adapter",
        "## 현지화",
        "## 로컬 조사 보고",
    ),
    "REQUIREMENTS.md": (
        "# 기능·비기능 요구사항",
        "## v0.1 필수 기능",
        "## 후속 기능: v0.1 완료 조건에 포함하지 않음",
        "## 비기능 기준",
        "## 변경 관리",
    ),
    "ARCHITECTURE.md": (
        "# 아키텍처",
        "## 설계 선택",
        "## 데이터 흐름",
        "## 인터페이스 경계",
        "## 스냅샷과 정합성",
        "## 오류와 자원",
    ),
    "TESTING.md": (
        "# 테스트 전략",
        "## 테스트 계층",
        "## fixture 정책",
        "## 실행 규칙",
        "## 현재 명령",
        "## 품질 게이트",
    ),
}

REQUIRED_LANGUAGE_CONTRACTS = {
    "DATA_CONTRACTS.md": (
        "SourceRef:",
        "Snapshot:",
        "LocalisationEntry:",
        "LocalisationCatalog:",
        "LocalisationResolution:",
        "TechnologyLocalisedName:",
        "reference_selections",
        "fallback(none|english|id)",
        "resolution(resolved|partial|unresolved|ambiguous)",
        "요청 언어 → 영어 → 원래 ID",
        "보호 영역",
        "영역 **밖의**",
        "정적 참조",
        "원문으로 보존",
        "`$KEY$`",
        "`partial`",
        "`unresolved`",
        "`ambiguous`",
        "`truncated`",
        "reader 기본 한도",
        "resolver 기본 한도",
        "LIMIT_EXCEEDED",
        "8 MiB",
        "16 MiB",
        "100,000",
        "## 저장 구조",
    ),
    "PARSING.md": (
        "요청 언어 → 영어 → 원래 ID",
        "보호 영역",
        "`$KEY$`",
        "정적 참조",
        "ambiguous",
        "partial",
        "LOC_DYNAMIC_UNSUPPORTED",
        "SourceRef",
        "LIMIT_EXCEEDED",
        "8 MiB",
        "64",
    ),
    "REQUIREMENTS.md": ("F-006", "F-007"),
    "ARCHITECTURE.md": ("LocalisationReader", "LocalisationResolver", "SnapshotRepository"),
    "TESTING.md": (
        "python -m pytest",
        "python -m ruff check .",
        "python scripts/check_harness.py",
    ),
}


def _verify_normative_markdown(name: str, contents: str) -> None:
    """Detect missing/duplicated titles and broken inline code, not only links."""

    expected = HEADING_CONTRACTS[name]
    assert contents.startswith(expected[0] + "\n"), name
    # A title injected after an unclosed inline code run might not be a
    # Markdown heading. Search the whole document to catch it as well.
    assert contents.count(expected[0]) == 1, name

    headings: list[str] = []
    fenced = False
    for number, line in enumerate(contents.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if re.fullmatch(r"#{1,3} .+", line):
            headings.append(line)
        # Normative docs require inline code pairs on each prose line.
        # Code fences are excluded.
        ticks = re.findall(r"(?<!`)(?<!\\)`(?!`)", line)
        assert len(ticks) % 2 == 0, (name, number, line[:100])
    assert not fenced, name
    assert headings == list(expected), (name, headings)

    for required in REQUIRED_LANGUAGE_CONTRACTS[name]:
        assert required in contents, (name, required)
    assert "$KEY# 데이터 계약 v1" not in contents, name
    assert "$KEY# 정적 파싱·현지화" not in contents, name


@pytest.mark.parametrize("document_name", tuple(HEADING_CONTRACTS))
def test_normative_documents_preserve_headings_inline_code_and_contracts(
    document_name: str,
) -> None:
    contents = (DOCS_ROOT / document_name).read_text(encoding="utf-8")
    _verify_normative_markdown(document_name, contents)


def test_r5_regression_detects_broken_reference_and_reinserted_heading() -> None:
    contents = (DOCS_ROOT / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    assert "영역 **밖의** `$KEY$`" in contents
    broken = contents.replace(
        "영역 **밖의** `$KEY$`", "영역 **밖의** `$KEY# 데이터 계약 v1", 1
    )
    with pytest.raises(AssertionError):
        _verify_normative_markdown("DATA_CONTRACTS.md", broken)


def test_r5_regression_detects_duplicate_sections_even_with_balanced_code() -> None:
    contents = (DOCS_ROOT / "DATA_CONTRACTS.md").read_text(encoding="utf-8")
    broken = contents.replace("## 출처\n", "## 출처\n\n## 출처\n", 1)
    with pytest.raises(AssertionError):
        _verify_normative_markdown("DATA_CONTRACTS.md", broken)


@pytest.mark.parametrize("name", ["DATA_CONTRACTS.md", "PARSING.md"])
def test_r5_regression_detects_missing_protected_reference_contract(name: str) -> None:
    contents = (DOCS_ROOT / name).read_text(encoding="utf-8")
    broken = contents.replace("`$KEY$`", "REFERENCE_SYNTAX_REMOVED")
    with pytest.raises(AssertionError):
        _verify_normative_markdown(name, broken)


def test_r5_regression_detects_broken_inline_code_in_other_normative_document() -> None:
    contents = (DOCS_ROOT / "PARSING.md").read_text(encoding="utf-8")
    broken = contents.replace("`$KEY$`", "`$KEY#", 1)
    with pytest.raises(AssertionError):
        _verify_normative_markdown("PARSING.md", broken)
