# TASK-003 configuration and doctor evidence

날짜: 2026-09-22  
검증 commit: `fe7a962a6940cc5f12ab13e0b8993fdbbdf7654a`  
GitHub Actions: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35730503602

## E-003 Invalid configuration

합성 임시 경로와 주입된 reader/access checker만 사용해 다음을 검증했다.

- 명시 config 누락 → `CONFIG_MISSING`
- malformed TOML → `CONFIG_INVALID_TOML`
- synthetic PermissionError reader → `CONFIG_UNREADABLE`
- unknown key → `CONFIG_UNKNOWN_KEY`
- invalid limit → `CONFIG_INVALID_LIMIT`
- `network.enabled=true` → `NETWORK_REJECTED`
- game_root 미지정 → `GAME_ROOT_REQUIRED`
- `STELLARIS_GAME_ROOT` 같은 환경값을 game_root로 사용하지 않음
- game_root는 read-only access mode만 검사
- missing/unreadable game/data 경로가 구조화 진단으로 반환됨

관련 테스트는 사용자 홈이나 실제 게임 폴더를 탐색하지 않는다.

## E-004 Runtime and path diagnostics

- TOML 상대 경로: config 파일 디렉터리 기준.
- CLI override 상대 경로: 현재 작업 디렉터리 기준.
- game_root/data_dir 동일, 부모, 자식 관계는 `PATH_REJECTED`.
- overlap doctor CLI는 exit 4.
- 일반 설정/경로 오류는 exit 3.
- application/Python/SQLite versions와 FTS5 bool을 report.
- FTS5 unavailable을 주입하면 warning으로 표시하고 exit 0.
- network state는 false이며 `NETWORK_DISABLED` info diagnostic.
- JSON stdout은 단일 객체.
- public report는 `<CONFIG_PATH>`, `<GAME_ROOT>`, `<DATA_DIR>`로 private path를 가릴 수 있음.

## 실제 실행

| 환경 | job | Python | pytest | Ruff | harness |
|---|---:|---:|---|---|---|
| ubuntu-latest | 106754601744 | 3.11.16 | 43 passed | success | success |
| windows-latest | 106754601852 | 3.13.15 | 43 passed | success | success |

양쪽 job의 최종 conclusion은 `success`였다.

## 범위와 한계

이 검증은 configuration/path policy와 local runtime doctor에 한정된다. `doctor`는 현재 source files를 재스캔하지 않는다. 실제 Stellaris 설치 경로, 게임 버전, DLC, mods, game file inventory는 사용하지 않았고 검증하지 않았다. FTS5 availability는 실행 환경의 SQLite capability이지 Stellaris 기능 상태가 아니다.
