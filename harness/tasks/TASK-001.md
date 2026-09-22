# TASK-001 Package and tooling

## 식별·범위

작업 ID: TASK-001  
제목: Package and tooling  
관련 기능 / 평가 ID: F-001 / E-001  
기준 브랜치와 commit: task/TASK-001-package-tooling / e394f5f10de4127375d2e597d5bbb5107e6a7d99  
선행 작업: 없음  
사용자 요청: TASK-001부터 순서대로 구현 시작.

이번에 구현할 것: Python 3.11+ 패키지 골격, 최소 CLI help/version, pytest/Ruff 개발 의존성, Linux/Windows CI의 clean editable install·import·help·test·lint 검증.  
이번에 구현하지 않을 것: Stellaris 데이터 파싱, 설정/doctor, 실제 게임 파일 접근, 검색/LLM/UI.  
수정·추가할 파일: pyproject.toml, src/stellaris_supporter/*, tests/*, .github/workflows/ci.yml, 환경/하네스 상태 문서.  
참조: docs/REQUIREMENTS.md F-001, docs/ENVIRONMENT.md, docs/BACKLOG.md, E-001.

## 수용 조건

- Python 3.11 이상 clean environment에서 `python -m pip install -e ".[dev]"` 성공.
- `python -c "import stellaris_supporter"` 성공.
- `stellaris-supporter --help`와 `--version` 성공.
- `python -m pytest`, `python -m ruff check .`, 문서 하네스 검사가 성공.
- 패키지/CLI 골격은 미구현 제품 기능을 구현된 것처럼 표시하지 않음.
- 런타임 의존성은 0으로 시작하고 개발 의존성 범위를 pyproject에 기록.
- 네트워크/게임 파일 접근은 수행하지 않음.

## 검증 계획

GitHub Actions의 ubuntu-latest/Python 3.11과 windows-latest/Python 3.13에서 clean install, import, help/version, pytest, Ruff, harness 검사를 실행한다. 실제 실행 전에는 E-001을 pass로 표시하지 않는다.

## 종료

구현과 원격 검증 후 evidence, E-001, TASK-001, state, 세션 기록을 갱신한다. 다음 작업은 TASK-002 Synthetic corpus.
