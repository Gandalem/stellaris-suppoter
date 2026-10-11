# 운영·복구 절차

TASK-013 브랜치에서는 `init/doctor/index/search/show/snapshots`를 기존 Python API에 연결하고 합성 E-026 회귀를 구현 중입니다. 독립 리뷰와 main CI 전에는 정식 릴리스 검증으로 취급하지 마세요. `refs/diff`와 실제 게임 엔진 실행은 여전히 미구현입니다.

## 정상 작업

설정/경로를 확인하고 doctor로 진단합니다. 첫 index는 개인 data_dir에 원문 캐시와 building snapshot을 만듭니다. 해시·파싱·출처·DB 정합성과 재검사를 통과한 뒤 active를 전환합니다. 조회에는 선택 snapshot과 버전/상태를 표시합니다. 게임 설치 폴더에는 쓰지 않습니다.

게임 업데이트 후에는 변경 여부를 확인하고 새 snapshot을 만듭니다. 파서·adapter·정책이 바뀌어도 새 분석이 필요합니다. 이전 snapshot을 삭제하지 않고 diff로 변경을 검토합니다. 오래된 결과를 사용 중이면 checked_at과 source 상태를 표시합니다.

## 실패별 대응

| 증상 | 안전한 대응 | 하지 말 것 |
|---|---|---|
| 경로 없음/permission | 사용자가 지정한 경로·읽기 권한 확인 | 전체 디스크 무작위 탐색, 관리자 권한 강요 |
| encoding/구문 오류 | 상대 파일·행·오류 유형 기록, 합성 재현 생성 | 오류 구간 삭제 후 성공 처리 |
| 파일이 수집 중 변경 | active 유지, 업데이트 종료 후 재시도 | 다른 시점의 파일을 최신 snapshot으로 결합 |
| 디스크 부족/쓰기 실패 | staging 중단, 이전 active 보존, 공간 안내 | 게임 파일 삭제 |
| 프로세스 취소/중단 | 다음 시작 시 building 상태 진단·재시작/폐기 선택 | building을 ready로 변경 |
| DB 손상/schema 불일치 | 개인 백업·버전 확인, 검증된 입력으로 재색인 | 구버전으로 임의 migration |
| FTS 없음/색인 불일치 | 진단·제한 fallback, 보조 색인 재생성 | 조용히 결과 없음 반환 |
| 동시 writer | 유한 timeout 후 오류·재시도 안내 | 끝없는 대기·잠금 파일 무조건 삭제 |
| 외부 수집 실패(후속) | 캐시 시점/실패 표시, 로컬 조회 유지 | 실패를 변경 없음으로 표시 |

## 백업·복구

DB를 열어둔 채 파일만 복사하는 대신 SQLite backup API 또는 writer가 없는 상태의 검증된 백업을 사용합니다. 관련 원문 캐시와 manifest도 함께 보존합니다. WAL 사용 여부에 맞는 절차를 구현 시 문서화합니다. 백업은 사용자 개인 위치에만 저장합니다.

앱 rollback과 데이터 rollback을 구분합니다. 이전 앱이 더 새 schema를 쓰지 않도록 차단합니다. 필요하면 이전 snapshot/백업으로 복구하거나 원본에서 재색인합니다. 실패한 staging 정리는 앱 소유의 data_dir 내부에서만 수행하고 game_root와 경로 경계를 다시 검증합니다.

TASK-010의 Python `SnapshotRepository`는 SQLite WAL/foreign_keys/250ms busy_timeout/FULL synchronous를 사용합니다.

PR #19 리뷰 보완 운영 경계: live 파일을 stage하면 원문 SHA뿐 아니라 그 순간의 game_root fingerprint와 **실제 root-relative 물리 경로**를 개인 SQLite에 남깁니다. 활성화에서 원본의 동일한 경로와 SHA를 다시 검사하므로 같은 bytes를 가진 다른 파일로 대체할 수 없습니다. SourceRef의 논리 상대 경로는 반드시 물리 위치와 같은 문자열일 필요가 없으며 base/mod source_id는 독립 namespace입니다. 다른 실제 루트의 모드 경로를 암묵적으로 허용하지 않습니다. 기존 PR의 초기 v1 소스 DB 레이아웃은 새 필수 컬럼이 없어 자동 업그레이드되지 않으므로 재색인하거나 별도 승인된 migration이 필요합니다. 전체 검사는 최초 열기·쓰기에, 일반 읽기에는 경량 schema/version/FK 검사만 수행합니다. cache pointer가 DB 기록과 불일치해도 active 포인터를 자동 전환하거나 데이터 오류를 조용히 보정하지 않습니다. 각 원본 blob의 원자적 파일 교체·SHA-256 검증 이후에만 building→ready/partial 상태가 가능하며, 활성화는 독립 `BEGIN IMMEDIATE` transaction에서 cache·manifest·출처 무결성을 다시 확인하고 settings의 active_snapshot 포인터만 변경합니다. 취소·오류·SQLite lock이 발생하면 rollback하고 이전 active를 유지합니다. 중단으로 남은 building은 다른 writer가 없다는 운영 확인 후 명시적 `recover_interrupted()`를 호출해 failed로 전환하며, 이를 자동 ready 처리하지 않습니다. 최초 DB 작성만 지원하고 이전/미래 schema는 구별해 거부합니다. `backup(name)`은 SQLite backup API로 DB 파일만 보존합니다. 실제 복구에는 cache/blobs 디렉터리의 필요한 SHA 원문도 별도로 보존해야 합니다. 전체 복구·migration을 구현했다고 해석하지 않습니다.

## 로그·진단

기본 로그에는 시각·작업 ID·단계·개수·시간·diagnostic code만 남깁니다. 원문·절대 경로·토큰·세이브는 제외합니다. debug도 명시 옵션이며 공개 첨부 전에 비식별화합니다. telemetry는 기본적으로 수집하지 않습니다.

문제 보고에는 OS/Python/SQLite/앱 버전, snapshot 지문의 비식별 요약, 재현 명령, expected/actual, 합성 재현, 로그의 안전한 부분을 넣습니다. 원문 업로드를 기본 지원 절차로 요구하지 않습니다.

## 완료 기록

운영 검증은 정상 동작뿐 아니라 실패 후 기존 active가 유지되는지, 원문이 변하지 않았는지, 개인정보가 새지 않았는지를 확인해야 합니다. 결과는 E-030~033과 릴리스 근거에 연결합니다.

## TASK-013 색인·조회 실패 복구

`index`는 명시 game_root 내부의 `common/technology/*.txt`, `localisation/korean/*.yml`, `localisation/english/*.yml`만 선택하고 inventory SHA와 안전하게 재수집한 bytes 및 root-relative 물리 경로를 비교합니다. `stage_from_results`가 파서·번역 진단과 partial을 보존하고, activation이 cache SHA와 동일한 live manifest를 재검증한 뒤 active 포인터만 트랜잭션으로 바꿉니다. `--allow-partial`은 미완성 구조에는 쓰일 수 있으나 원본 변경·경로·한도/DB 무결성 오류 우회에는 적용하지 않습니다. 기존 ready snapshot 재활성화도 live/cached bytes를 재검증합니다. building/failed는 재활성화 대상이 아닙니다. 

기술 ID show는 AnswerService의 출처 검사를 실행하며 연구 비용·확률을 계산하지 않습니다. `snapshots`는 limit 1~100의 읽기 전용 목록을 반환합니다. 종료 코드·JSON/text 출력과 충돌되는 문구가 있으면 [CLI.md](CLI.md)를 우선합니다. 실제 게임 호환성과 hostile same-path 교체 완전 방어, cold time·peak RSS는 검증되지 않았습니다.
