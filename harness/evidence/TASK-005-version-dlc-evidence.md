# TASK-005 version and DLC evidence

날짜: 2026-09-23  
기능 candidate: `44ff8d3e7aa0b9de03888a38cb19e65a483a916e`  
기준 main: `472aad700e24e03b20081f13b653502b673c7d00`

## 범위

이 작업은 실제 Stellaris 설치의 현재 버전/DLC를 알아내는 작업이 아니다. snapshot 계약에 사용할 evidence model을 구현한다.

### Version evidence

- `game_version`과 `game_version_source`: metadata|user_reported|unknown.
- `build_id`와 별도 source.
- `branch`: stable|beta|unknown과 별도 source.
- metadata evidence가 있으면 user report보다 우선하지만 충돌을 숨기지 않고 diagnostic.
- build ID에서 patch/version label을 추론하지 않음.
- version evidence가 없으면 `game_version=null` + `VERSION_UNKNOWN`.

### DLC evidence

각 DLC는 installed/owned/enabled를 각각 독립 `TriStateEvidence`로 가진다.

- value: true|false|null
- source: filesystem|platform|launcher|user_reported|unknown
- evidence: optional detail

known true/false는 source=unknown으로 저장할 수 없다. 한 필드의 evidence를 다른 필드로 자동 전파하지 않는다. 예를 들어 filesystem presence가 installed=true의 근거가 될 수 있어도 owned/enabled는 null/unknown으로 남을 수 있다.

## E-007 Version uncertainty

검증 사례:
- metadata/user-reported 둘 다 없음.
- build ID만 metadata로 존재.
- user-reported version/branch만 존재.
- metadata/user version conflict.
- metadata/user branch conflict.
- unsupported branch label.

결과:
- unknown과 user_reported가 구분됨.
- build ID는 game version으로 승격되지 않음.
- metadata conflict precedence와 warning이 deterministic함.

## E-008 DLC state separation

검증 사례:
- installed=true(filesystem), owned/enabled unknown.
- installed/owned/enabled 각각 다른 source.
- installed=false + enabled=true conflict.
- known bool + unknown source 거부.
- null state가 platform/launcher checked evidence를 가질 수 있음.
- serialization에서 세 필드가 독립적으로 유지됨.

## CI

Package and tooling run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35750105437

| 환경 | 전체 pytest | versioning | Ruff | harness |
|---|---:|---:|---|---|
| Ubuntu / Python 3.11.16 | 94 passed | 13 passed | success | success |
| Windows / Python 3.13.15 | 93 passed + 1 POSIX-only inventory skip (94 collected) | 13 passed | success | success |

Windows skip은 TASK-004의 surrogateescape filename regression으로 TASK-005 테스트가 아니다.

## 미검증

- 실제 게임 metadata 파일 위치/형식.
- 실제 installed build/version/branch.
- Steam/launcher DLC ownership API.
- 사용자의 실제 DLC owned/enabled 상태.
- 현재 공식 최신 패치.

따라서 `latest_game_version`은 null을 유지한다. actual local acceptance와 최신 공식 source sync는 후속 작업이다.

## 상태

E-007 pass.  
E-008 pass.  
TASK-005는 review/main integration 전까지 doing.  
F-003은 TASK-005 main integration 전까지 in_progress.
