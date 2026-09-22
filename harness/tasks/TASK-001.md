# TASK-001 Package and tooling

## 식별·범위

작업 ID: TASK-001  
제목: Package and tooling  
관련 기능 / 평가 ID: F-001 / E-001  
기준 브랜치와 시작 commit: task/TASK-001-package-tooling / e394f5f10de4127375d2e597d5bbb5107e6a7d99  
선행 작업: 없음  
사용자 요청: TASK-001부터 순서대로 구현 시작.

구현한 것: Python 3.11+ 패키지 골격, 최소 CLI help/version, pytest/Ruff 개발 의존성, Linux/Windows CI의 clean editable install·import·help·test·lint 검증.  
구현하지 않은 것: Stellaris 데이터 파싱, 설정/doctor, 실제 게임 파일 접근, 검색/LLM/UI.  
주요 파일: pyproject.toml, src/stellaris_supporter/*, tests/test_package.py, .github/workflows/ci.yml.  
참조: docs/REQUIREMENTS.md F-001, docs/ENVIRONMENT.md, docs/BACKLOG.md, E-001.

## 수용 조건 결과

- Python 3.11+ clean environment의 editable install: 통과.
- import와 `stellaris-supporter --help/--version`: 통과.
- `python -m pytest`: Linux/Windows 모두 22 tests passed.
- `python -m ruff check .`: Linux/Windows 모두 통과.
- `python scripts/check_harness.py`: Linux/Windows 모두 통과.
- 패키지 골격은 미래 제품 subcommand를 광고하지 않음.
- 런타임 외부 의존성 0; build/dev dependency 범위는 pyproject에 기록.
- 실제 게임 파일 접근·모델/API 호출 없음.

## 검증 이력

최종 검증 대상 commit: `ed1e9027c0dc61c302f705443550d8d557266cc5`  
GitHub Actions run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35727223388

- Ubuntu / Python 3.11.16 / job 106743717971: 모든 단계 success.
- Windows / Python 3.13.15 / job 106743718187: 모든 단계 success.
- pytest: 각 환경 22 passed.
- Ruff: All checks passed.
- 하네스: `harness_valid: true`.

초기 실행 두 번은 scaffold help 테스트가 일반 도움말 단어를 미래 subcommand 이름으로 오인해 실패했고 테스트를 구조 기반 검증으로 수정했다. 세 번째 실행에서는 테스트는 통과했으나 기존 하네스 코드의 Ruff baseline이 드러나 E501을 명시적으로 제외하고 import order를 정리했다. 최종 run 4에서 양 플랫폼 전체 성공.

## 종료

상태: done  
평가 E-001: pass  
근거: [clean setup evidence](../evidence/TASK-001-clean-setup.md)  
검토: self_review  
다음 작업: TASK-002 Synthetic corpus.
