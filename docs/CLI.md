# CLI 계약 v0.1

`doctor`는 TASK-003에서 구현됐습니다. 나머지 제품 명령은 아직 구현되지 않았고 TASK-013이 기본 CLI 흐름, TASK-015가 refs, TASK-016이 diff를 확장합니다. 현재 help에는 구현된 `doctor`만 제품 subcommand로 표시합니다.

## 공통

실행 이름은 stellaris-supporter입니다. 현재 전역 옵션은 subcommand 앞에 둡니다: `--config PATH`, `--format text|json`, `--game-root PATH`, `--data-dir PATH`, `--language CODE`. 기본 출력은 text입니다. `--verbose`는 후속 CLI 작업에서 추가합니다. JSON stdout에는 객체 하나만, 로그·진행률은 stderr에 출력합니다. JSON 모드에서는 색상/진행률을 끕니다. 개인 경로·키·원문 전체는 공개 로그에서 제외합니다.

설정 파일을 명시할 수 있으며 기본 위치와 경로 해석 규칙은 [환경 문서](ENVIRONMENT.md)에 확정했습니다. `doctor`는 source 파일을 스캔하지 않고 설정·경로·Python/SQLite/FTS5·네트워크 비활성 상태만 검사합니다. `--check-sources`는 inventory 구현 후 추가합니다.

| 명령 | 핵심 인자 | 동작 |
|---|---|---|
| init | --game-root PATH --data-dir PATH | 안전한 설정 작성; 기존 파일은 확인 없이 덮지 않음 |
| doctor | 현재 추가 인자 없음 | 설정·경로·application/Python/SQLite/FTS5·network off 확인; source 재검사는 아직 하지 않음 |
| index | --allow-partial 선택 | 수집·parse·번역·DB 생성, 검증 후 활성화 |
| search TEXT | --kind KIND --snapshot ID --limit N 선택 | 이름·ID·별칭 검색 |
| show GAME_ID | --kind KIND --snapshot ID 선택 | 모든 일치 정의·근거·충돌 반환 |
| refs GAME_ID | --direction in\|out --depth N --snapshot ID 선택 | 정적 참조; 기본 out/depth 1, 최대 8 |
| snapshots | 없음 | snapshot 상태·버전·생성/검사 시각 |
| diff OLD NEW | snapshot ID 두 개 | 파일·엔티티 변화; 엔진 의미 변화로 과장하지 않음 |

kind는 registry의 범주만 허용합니다. snapshot 미지정 시 active를 사용하고 둘 다 없으면 종료 코드 3입니다. ask, sync, save, simulate, serve는 후속 기능이며 v0.1 help에 구현된 것처럼 표시하지 않습니다.

## 목표 사용 예

```sh
stellaris-supporter --config ./stellaris-supporter.local.toml init --game-root '<GAME_ROOT>' --data-dir '<DATA_DIR>'
stellaris-supporter --config ./stellaris-supporter.local.toml doctor
stellaris-supporter --config ./stellaris-supporter.local.toml index
stellaris-supporter --config ./stellaris-supporter.local.toml search '합성 연구 알파' --kind technology
stellaris-supporter --config ./stellaris-supporter.local.toml --format json show demo_tech_alpha
stellaris-supporter --config ./stellaris-supporter.local.toml refs demo_tech_alpha --depth 2
```

Windows 경로·인용 부호 예시는 실제 실행 후 추가합니다. 합성 ID는 게임에 존재한다는 의미가 아닙니다.

## 출력과 종료 코드

출력 구조는 [데이터 계약](DATA_CONTRACTS.md)을 따릅니다. text에도 snapshot, context_kind, 버전/unknown, 파일·행, fallback·부분 성공이 포함됩니다. 원문은 필요한 짧은 구간만 표시합니다.

| 코드 | 의미 |
|---|---|
| 0 | 정상; not_found 또는 명시 허용 partial은 구조화 상태로 반환 |
| 2 | 잘못된 인자·질의·미지원 subcommand |
| 3 | 설정/경로/선택 snapshot 부재 또는 접근 불가 |
| 4 | 안전 경계·입력 한도 위반 |
| 5 | 원문 변화·decoding/parse 실패로 index 활성화 불가 |
| 6 | 저장소·스키마·트랜잭션 오류 |
| 7 | 후속 외부 provider 필수 작업 실패 |
| 130 | 사용자 취소 |

오프라인 정적 기능은 provider 오류로 실패하면 안 됩니다. 결과 없음은 장애가 아니므로 exit 0입니다. --allow-partial은 보안 실패·경로 오류를 무시하지 않습니다. 중단된 index는 기존 active를 유지합니다.
