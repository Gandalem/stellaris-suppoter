# CLI 계약 v0.1 — TASK-013 수직 통합 후보

현재 TASK-013 개발 브랜치에 구현된 명령은 **init, doctor, index, search, show, snapshots**입니다. 실제 패키지 검증·독립 기술 리뷰·main 통합 이전의 개발 기능이며, Python API의 이전 TASK-003~012 성공과 구분합니다. 실제 게임 설치본에서 호환성은 아직 검증되지 않았습니다.

## 공통 실행

`stellaris-supporter` 또는 `python -m stellaris_supporter`. 전역 `--config PATH`, `--format text|json`, `--game-root PATH`, `--data-dir PATH`, `--language ko|en|korean|english`는 subcommand 앞뒤에 사용할 수 있습니다. 같은 옵션을 앞뒤 모두 지정한 경우 **subcommand 뒤 값이 우선**합니다. 설정 파일 TOML보다 CLI override가 우선이며, TOML 상대 경로는 설정 파일 폴더, CLI 상대 경로는 현재 작업 폴더 기준입니다.

| 명령 | 인자 | 구현 범위 |
|---|---|---|
| init | --game-root PATH [--data-dir PATH] | 기존 파일 덮어쓰기 없는 안전한 TOML 작성, network=false |
| doctor | 없음 | 설정/경로/Python/SQLite/FTS5 네트워크 비활성 진단; 전체 index는 안 함 |
| index | [--allow-partial] | common/technology .txt 및 localisation/korean·english .yml만 안전 수집·검증·색인/활성화 |
| search TEXT | [--kind technology] [--snapshot SHA] [--limit 1..100] | SearchService의 정확 ID·한/영 이름·짧은/부분 검색·동명 정의 |
| show GAME_ID | [--kind technology] [--snapshot SHA] [--limit 1..100] | **정확한 게임 ID만** AnswerService의 R1–R6 검증을 거쳐 정적 표현식·SourceRef 반환 |
| snapshots | [--limit 1..100] [--offset 0..100000] | 제한된 read-only 목록, active·status·문맥·버전 |

`refs`는 TASK-015, `diff`는 TASK-016에서 구현합니다. 아직 없는 `ask/sync/save/simulate/serve`는 제공하지 않습니다. 명시적 snapshot 없이 search/show하면 요청 시작 시 active가 고정됩니다. snapshot이 없으면 종료 3입니다.

## 합성 테스트에서 사용하는 호출 형태

Linux:
```sh
stellaris-supporter --config ./private/config.toml init --game-root '/path/to/synthetic-game' --data-dir '/path/to/private-data'
python -m stellaris_supporter --config ./private/config.toml --format json doctor
python -m stellaris_supporter --config ./private/config.toml --format json index
stellaris-supporter --config ./private/config.toml --format json search '합금 연구'
stellaris-supporter --config ./private/config.toml --format json show demo_tech
stellaris-supporter --config ./private/config.toml --format json snapshots
```
Windows PowerShell (경로·인용은 개인 환경에 맞게 교체):
```powershell
python -m stellaris_supporter --config '.\private\config.toml' init --game-root 'C:\synthetic game' --data-dir 'C:\private data'
python -m stellaris_supporter --config '.\private\config.toml' --format json index
python -m stellaris_supporter --config '.\private\config.toml' --format json search 'demo_tech'
python -m stellaris_supporter --config '.\private\config.toml' --format json show 'demo_tech'
```
위 PATH는 설명용 플레이스홀더입니다. 실제 개인 절대 경로나 게임 원문을 공개 evidence에 포함하지 않습니다.

## 안전성·출력·오류

index는 안전한 inventory SHA → 실제 live source O_NOFOLLOW(가능한 OS) 파일 캡처 SHA/크기·경로 검증 → 결정적 정책 identity → parser/adapter·localisation → `stage_from_results()` → `activate(...,sources=...)`로 실행합니다. config·DB·cache는 game_root 밖의 명시적 data_dir에만 기록합니다. 동일한 정상 snapshot은 재활성화 시에도 **현재 live manifest와 캐시**를 다시 검증합니다. `--allow-partial`은 parsing/translation partial에만 적용하며 PATH_REJECTED·SOURCE_CHANGED·LIMIT_EXCEEDED를 우회할 수 없습니다. 원본의 같은 경로를 공격적으로 교체하는 OS 수준 TOCTOU 위험은 완전히 제거한 것은 아닙니다.

JSON 모드는 stdout에 유일한 객체 하나(기본 schema_version 1, command, status, diagnostics 포함), 한국어를 ensure_ascii=False로 출력합니다. 오류·로그는 stderr와 구분하고 안전 오류는 내부 traceback이나 개인 원문을 출력하지 않습니다. `doctor`는 기존 운영자를 위한 로컬 진단 계약을 보존하므로 **명시한 개인 경로를 출력할 수 있습니다**. 공개 증거에는 `DoctorReport.to_dict(public=True)` 등 별도 비식별 직렬화를 사용하세요.

검색 hit와 show facts는 상대 경로, source ID·SHA, byte_start/byte_end, 실제 line_start/line_end, snapshot_id를 구분합니다. `raw_expression`은 엔진 계산이 아니라 **검증된 원문 표현식**입니다. E-026은 직접 만든 합성 fixture만 사용합니다.

| 종료 코드 | 의미 |
|---|---|
| 0 | 정상, not_found, 명시 승인된 partial |
| 2 | 잘못된 인자/질의, 미지원 명령 |
| 3 | 설정·경로·snapshot 부재 |
| 4 | 안전 경계·입력 한도 위반 |
| 5 | 원본 변경·decoding/parse로 인한 활성화 불가 |
| 6 | SQLite·schema·저장 또는 알 수 없는 안전한 내부 오류 |
| 7 | 후속 provider 실패 — TASK-013에서는 사용하지 않음 |
| 130 | 사용자 취소 |

구현 결과는 `harness/evidence/TASK-013-cli-vertical-slice.md`에 CI 실제 실행을 확인한 다음 연결합니다. 동일 입력·동일 정책은 동일 snapshot ID를 생성하며 절대경로/시간을 ID에 혼합하지 않습니다.
