# TASK-003 Configuration and doctor

## 식별·범위

작업 ID: TASK-003  
제목: Configuration and doctor  
관련 기능 / 평가 ID: F-002 / E-003, E-004  
기준 브랜치와 시작 commit: task/TASK-003-configuration-doctor / d748e218c33b2d98de95f3da1b7f7cd87d469195  
최종 기능 검증 commit: fe7a962a6940cc5f12ab13e0b8993fdbbdf7654a  
선행 작업: TASK-001 done  
사용자 요청: TASK-003 — Configuration and doctor 구현.

## 구현한 것

- stdlib `tomllib` 기반 TOML 설정 로딩과 strict key/type 검증.
- CLI override → TOML → 안전한 기본값 순서.
- game_root 자동 탐색 금지.
- Windows/Linux/macOS best-effort 기본 config/data 위치 계산.
- TOML 상대 경로는 config 디렉터리, CLI 상대 경로는 cwd 기준.
- game_root/data_dir 존재·종류·접근성 검사.
- game_root/data_dir 동일 또는 부모/자식 overlap 거부.
- game_root에는 읽기 권한만 요구하고 data_dir에는 읽기/쓰기 요구.
- `network.enabled=true` 거부; runtime network state는 false.
- limits 기본값과 양의 정수 검증.
- Python/SQLite/FTS5/application version capability 진단.
- `stellaris-supporter doctor` text/JSON 출력과 종료 코드.
- public report 직렬화 시 config/game/data 절대 경로 placeholder 치환.
- `config.example.toml`, CLI/environment/decision/agent 문서 갱신.

구현하지 않은 것:
- 게임 설치 자동 탐색.
- 게임 버전/DLC 판별(TASK-005).
- source 재스캔, inventory, parser/index/search.
- 네트워크 접근, 외부 provider, config 자동 작성(init는 TASK-013).

## 수용 조건 결과

- missing/malformed/unreadable/unknown/invalid setting → structured diagnostic: 통과.
- 환경변수의 임의 game path를 사용하지 않음: 통과.
- TOML/CLI 상대 경로 기준 분리: 통과.
- game/data overlap → `PATH_REJECTED`, safety exit 4: 통과.
- missing/access 문제 → exit 3 계열 진단: 통과.
- app/Python/SQLite/FTS5/network-disabled report: 통과.
- FTS5 부재 주입 시 warning + exit 0 fallback 상태: 통과.
- JSON stdout single object: 통과.
- public serialization path redaction: 통과.
- Linux/Windows 회귀/정적/하네스 검사: 통과.

## 검증

GitHub Actions run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35730503602

- Ubuntu / Python 3.11.16 / job 106754601744: 43 tests passed, Ruff success, harness success.
- Windows / Python 3.13.15 / job 106754601852: 43 tests passed, Ruff success, harness success.
- 양쪽 모두 install, pip check, import, CLI help/version 단계도 success.

개발 중 CLI help assertion 두 건과 Ruff import/style 두 건을 실제 CI에서 발견해 플랫폼/폭 독립 테스트와 import 정렬로 교정했다. 완료 근거는 실패 run이 아니라 위 최종 성공 run만 사용한다.

## 종료

상태: done  
평가 E-003: pass  
평가 E-004: pass  
F-002: verified  
근거: [configuration and doctor evidence](../evidence/TASK-003-configuration-doctor.md)  
검토: self_review  
다음 작업: TASK-004 Safe inventory.
