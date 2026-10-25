# TASK-033 — 로컬 데이터 저장 2안

2026-10-25, Windows / Python 3.12.14 / SQLite 3.53.1. 사용자 지시에 따라 전체 기능 코드 작성 후 필수 검사만 실행했다. 기존 로컬 변경을 보존했고 커밋·푸시·PR·병합·배포는 실행하지 않았다.

## 구현 결과

- 파일 정체성·내용 해시·파서 버전으로 구분하는 영구 번역 카탈로그. 1,000행/8MiB 배치, 24MiB 원문 LRU, 200만 번역행/2GiB 디스크 한도. 기존 파일별/입력/참조 한도 유지.
- 반복 경고는 코드·심각도별 총계와 최초 3개 샘플을 저장한다. 게임 lexical 호환 모드의 내부 따옴표 및 n/t/r escape를 처리하고 원문 span을 보존한다.
- 전체 번역 저장과 기존 API용 참조 집합을 분리한다. 누락 키·언어 대체·중복을 포함한 파생 의존관계를 기록하고 현재 스냅샷 출처로 재결합한다. 두 언어의 이름은 저장한 투영으로 조회한다.
- 검색 투영을 fingerprint/hash/size로 확인해 재시작 후 재사용한다. 손상 시 원본에서 복구한다. 기존 v1 스냅샷과 고정 카드는 보존한다.
- 검색과 색인은 별도 worker/DB 연결로 동작한다. 단일 writer lock, 취소·중단 상태, 비활성 실패 staging 재시도, 완료 후 원본 재확인/CAS 활성화를 유지한다.
- 전체 번역 비교는 키 그룹을 스트리밍한다. 불완전 소스의 추가·삭제는 확정하지 않는다.

## 실제 설치 데이터

개인 검사 전용 data_dir에서 실행했다. 게임 원본은 읽기 전용이며 기본 사용자 DB·설정은 변경하지 않았다. launcher metadata는 Cygnus v4.5.2 (9776); API의 게임 버전/브랜치는 여전히 unknown이다.

499개 파일, 기술 692개, 번역 **297,964개**를 저장했다. 초기 빌드와 strict partial 거절 후 명시적 재시도를 합친 시간은 **300.757초**였다. 일부 검사는 동시에 실행되어 독점 성능 측정이 아니다. 색인 Python 프로세스 peak working set은 **136,548,352 bytes**였으며 전체 Qt 앱 메모리 수치가 아니다.

최종 코드의 재색인은 **6.525초**, parsed 0 / reused 499였다. 재시작한 별도 프로세스에서 projection 재생성을 금지한 상태로 첫 검색 **165.230ms**, 후속 검색 **5.497ms**를 측정했다. 이 시간은 모듈 import·repository 생성·앱 전체 시작을 포함하지 않는다. 한·영 이름/ID 조회, 원문 출처 11개, 선행 관계 1개가 일치했다.

원문 일부는 정적 분석 범위를 벗어나 **32개 번역 파일이 partial**이다. 기본 색인은 이를 자동 활성화하지 않으며 명시적 partial 동의를 유지한다. 같은 실제 스냅샷 비교는 23.411초/변경 0/partial로 종료했고 불완전한 요약을 완전 성공으로 표시하지 않았다.

## 필수 검사

실행은 `.venv/Scripts/python.exe -m pytest ... -q --basetemp .venv/<개별 신규 폴더>`이며 아래 묶음은 겹치므로 합산하지 않는다.

- `tests/test_disk_storage.py tests/test_incremental_diff.py`: **34 passed**, 117.41초.
- `test_retrieval.py test_answers.py test_cli_vertical.py test_references_cli.py test_normative_document_integrity.py`: 최초 **166 passed / 1 failed**, 254.22초. 실패는 기존 인코딩 손상을 partial 동의로 허용하는 fixture였다. 유효 UTF-8의 불완전 문법으로 동의 검사를 유지하고 인코딩 손상 거절 검사를 별도 추가했다.
- 최종 `test_disk_storage.py test_cli_vertical.py::test_e026_partial_localisation_can_only_activate_with_consent test_storage_snapshots.py`: **92 passed**, 80.02초. 손상 복구, 외부 형식 DB 보존, 취소/같은 입력 재시도, 누락 키/중복/언어 대체, 이전 스냅샷, 색인 중 검색, 기존 SQLite 저장 경계를 포함한다.
- 최종 `test_normative_document_integrity.py`: **12 passed**.
- 이전 영향 묶음의 소스 소실 코드·언어 변경 identity·캐시 파서 재실행·파서 캐시 namespace 실패를 수정했다. 상세 결과는 기계 기록과 이번 세션에 연결한다.
- repository-wide Ruff, wheel build, Windows PyInstaller onedir build 통과. 패키지의 `--smoke --preferences <private path>` 실행 종료 코드 **0**. 별도 색인 worker를 포함한 종료 경로를 사용했다.

실제 게임 위 단축키·클릭/키 입력 통과·다중 모니터 수용은 이번 변경의 통과 근거에 포함하지 않는다. 이전 UI 도구 초기화 권한 오류로 E-046/E-048은 not_run을 유지한다. 전체 TASK-033과 원격 CI/병합을 완료로 올리지 않았다.

기계 결과: [JSON](TASK-033-data-option-2.json). 구현 계약: [로컬 데이터 저장 2안](../../docs/DATA-STORAGE-OPTION-2.md).
