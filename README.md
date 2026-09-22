# Stellaris Supporter

사용자가 설치한 Stellaris 데이터에 근거하여 한국어로 검색하고 설명하는 로컬 우선 도우미.

> **상태: TASK-001 개발 환경, TASK-002 합성 corpus, TASK-003 설정/doctor까지 구현됨. 실제 게임 inventory/parser/search 기능은 아직 구현되지 않았습니다.**
> 기준일: 2026-09-22 (Asia/Seoul). 이 날짜는 문서 작성일이며 게임 데이터 검증일이 아닙니다.
> 저장소 이름 `stellaris-suppoter`는 기존 이름을 유지합니다. Python 패키지명은 `stellaris_supporter`, 예정 CLI는 `stellaris-supporter`입니다.

## 시작점

- [전체 문서 지도](docs/INDEX.md): 역할별 읽기 순서와 문서의 권위.
- [에이전트 작업 규칙](AGENTS.md): 매 세션 시작·종료, 금지 사항, 검증·보고 규칙.
- [제품 범위](docs/PRODUCT.md) / [기능 명세](docs/REQUIREMENTS.md): 무엇을 먼저 만들고 무엇을 보류하는가.
- [작업 목록](docs/BACKLOG.md) / [작업 원장](harness/tasks.json): 의존성이 있는 구현 순서와 완료 조건.
- [환경 준비](docs/ENVIRONMENT.md): 필요한 프로그램·데이터·사용자 확인 사항.
- [하네스 사용법](harness/README.md): 기능·작업·평가·상태 기록 연결.

## 첫 번째 목표

게임 설치 경로 지정 → 안전한 파일 목록·해시 생성 → 스크립트 정적 파싱 → 번역 연결 → SQLite 색인 → 한국어/영문/ID 검색 → 원문 파일·행·스냅샷을 표시하는 답변.

첫 수직 슬라이스는 **합성 기술 데이터 하나를 검색하고 정확한 원문 위치와 함께 출력하는 것**입니다. 이어서 사용자 로컬 설치 데이터의 기술·함선 부품·건물·직업·특성·정부 관련 항목·전통·승천·이벤트로 범위를 넓힙니다. 폴더와 실제 구문은 로컬 조사 후 매핑하며, 이벤트 실행 결과나 게임 엔진 전체를 흉내 내지는 않습니다.

v0.1은 인터넷·API 키·Codex·GPU 없이 **개발자가 만든 합성 fixture를 이용한 개발과 테스트**, 그리고 사용자의 로컬 게임 파일 검색이 가능하도록 설계합니다. 이는 아직 달성한 기능이 아니라 릴리스 조건입니다. 모델 연결, 공식 공지 수집, 모드 적용 해석, 세이브 분석, 전투 계산은 후속 단계입니다.

## 정확성 원칙

설치된 게임 데이터, 공식 정식 패치, 베타·개발 예정 정보, 커뮤니티 의견을 섞지 않습니다. 출처 없는 수치와 등장 확률을 만들지 않습니다. 설치 파일이 있어도 DLC 소유·활성화나 현재 세이브의 적용 상태를 단정하지 않습니다. 게임 파일에서 읽은 정적 정의와 실제 엔진 실행 결과도 구별합니다.

이전 대화에서 제시된 구체적인 패치 번호·코드명·출시 일정은 이 저장소에서 검증된 기준으로 채택하지 않습니다. 최신 버전 번호는 확인 전 `unknown`이며, [불확실성 원장](docs/UNKNOWNS.md)과 [출처 목록](docs/SOURCES.md)을 사용합니다.

## 지금 실행할 수 있는 것

Python 3.11 이상에서 개발 환경을 설치하고 현재 패키지 골격을 확인할 수 있습니다.

```sh
python -m venv .venv
python -m pip install -e ".[dev]"
stellaris-supporter --help
stellaris-supporter --version
stellaris-supporter --config ./stellaris-supporter.local.toml doctor
python -m pytest
python -m ruff check .
python scripts/check_harness.py
python scripts/generate_synthetic_corpus.py --output ./tmp-synthetic
```

현재 `stellaris-supporter`는 help/version과 `doctor`를 제공합니다. `doctor`는 설정, game/data 경로 경계, Python/SQLite/FTS5, network off 상태만 확인하며 게임 파일을 스캔하지 않습니다. [합성 corpus](tests/fixtures/synthetic/README.md)는 parser/localisation 개발용 테스트 입력이며 실제 게임 데이터가 아닙니다. inventory, parser, 검색, 실제 게임 데이터 분석, 모델 연결은 아직 없습니다.

## 프로젝트 상태 관리

제품 기능 상태의 단일 원장은 [features.json](harness/features.json), 작업 상태는 [tasks.json](harness/tasks.json), 다음 작업은 [state.json](harness/state.json)입니다. TASK-001~003은 완료됐고 E-001~004는 실행 근거와 함께 통과했습니다. F-002 설정·진단은 `verified`, F-004/F-006은 합성 corpus만 준비된 상태라 `in_progress`입니다. 실제 inventory/parser/search와 게임 호환성은 아직 검증되지 않았습니다.

## 데이터와 공개 저장소

실제 게임 원문, DLC·모드 원문, 세이브, 색인 DB, 개인 경로, API 키를 이 공개 저장소에 커밋하지 않습니다. 테스트에는 직접 만든 합성 데이터만 사용합니다. 게임 설치 폴더는 읽기 전용으로 취급합니다. [보안 정책](SECURITY.md)을 따르세요.

이 프로젝트는 비공식 도구입니다. 라이선스는 소유자가 결정하기 전까지 임의로 부여하지 않습니다. 외부 의존성·데이터 이용 조건은 별도로 검토합니다.
