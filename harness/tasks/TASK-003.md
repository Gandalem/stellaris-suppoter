# TASK-003 Configuration and doctor

## 식별·범위

작업 ID: TASK-003  
제목: Configuration and doctor  
관련 기능 / 평가 ID: F-002 / E-003, E-004  
기준 브랜치와 시작 commit: task/TASK-003-configuration-doctor / d748e218c33b2d98de95f3da1b7f7cd87d469195  
선행 작업: TASK-001 done  
사용자 요청: TASK-003 — Configuration and doctor 구현.

이번에 구현할 것:
- stdlib `tomllib` 기반 설정 로딩과 구조 검증.
- CLI override → TOML → 안전한 기본값 순서.
- game_root 자동 탐색 금지.
- OS별 기본 config/data 위치 계산.
- game_root/data_dir 존재·종류·접근성 검사.
- game_root/data_dir 동일 또는 부모/자식 overlap 거부.
- network.enabled=false 강제.
- limits 기본값과 범위 검사.
- Python/SQLite/FTS5/application version capability 진단.
- `stellaris-supporter doctor` text/JSON 출력과 종료 코드.
- 개인 절대 경로 redaction 가능한 public diagnostic representation.
- 합성/임시 디렉터리만 사용하는 E-003/E-004 테스트.

이번에 구현하지 않을 것:
- 게임 설치 자동 탐색.
- 게임 버전/DLC 판별(TASK-005).
- source 재스캔 또는 parser/index/search.
- 네트워크 접근, 외부 provider, config 파일 자동 생성(init는 TASK-013).

## 수용 조건

- missing/malformed/unknown/invalid setting이 structured diagnostic으로 실패.
- 명시되지 않은 game_root를 환경변수나 홈 검색으로 추측하지 않음.
- TOML 상대 경로는 config 파일 디렉터리를 기준으로 결정적으로 해석.
- CLI override 경로는 현재 작업 디렉터리 기준으로 해석.
- data_dir와 game_root가 같거나 어느 쪽이 다른 쪽의 부모/자식이면 PATH_REJECTED.
- runtime doctor가 app/Python/SQLite/FTS5와 network disabled를 보고.
- FTS5 부재는 fallback-capable warning이며 doctor 자체를 실패시키지 않음.
- JSON stdout은 객체 하나, path values는 기본 local output에서 명시적으로 노출되나 public evidence에는 placeholder만 사용.
- Linux/Windows에서 E-003/E-004 테스트 통과.

## 검증 계획

```sh
python -m pytest
python -m ruff check .
python scripts/check_harness.py
stellaris-supporter --help
stellaris-supporter --format json --config <synthetic.toml> doctor
```

## 종료

완료 시 TASK-003=done, E-003/E-004=pass. F-002는 연결 작업이 TASK-003 하나이므로 검증 결과가 충분하면 verified로 전환한다. 다음 번호 작업은 TASK-004 Safe inventory.
