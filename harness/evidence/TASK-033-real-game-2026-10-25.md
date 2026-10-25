# TASK-033 — 실제 설치·실행 게임 검사 2026-10-25

사용자가 게임을 실행하고 테스트를 요청했다. 작업 브랜치 task/desktop-overlay-option-1, 기준 HEAD dc6f031c1eca781b53ad224bc5c881cc01465938 + 기존 로컬 변경. self_review. [구조화 결과](TASK-033-real-game-2026-10-25.json).

## 결과

- 실제 실행 창의 전체 실행 경로/PID/HWND 식별 성공. 클라이언트 2560×1440, DPI 144. 창 스타일은 테두리 없음/전체 화면 중 하나이며 독점 전체 화면 여부는 확인하지 않았다. 설치 launcher-settings의 버전은 Cygnus v4.5.2 (9776). 실제 게임 UI 버전 표시를 대조하지 않았다.
- 사용자 앱 DB는 active가 없고 스냅샷 목록이 비어 있었다. 테스트는 별도 개인 DB에 실행해 사용자 DB/설정/카드를 바꾸지 않았다.
- 실제 기본 색인 index_technologies(strict, events 제외)가 80.331초 뒤 LIMIT_EXCEEDED로 실패했다. 성공한 색인/한영 검색으로 보고하지 않는다.
- 입력 규모: 기술 35파일/530772 bytes, 한국어 번역 232파일/17237214 bytes, 영어 번역 232파일/15396345 bytes.
- 별도 번역 집계에서 현재 파서가 수집한 entries 296328, incomplete 문서 100개. unsupported escape 26554, trailing syntax 1466, unsupported syntax 2448, LIMIT_EXCEEDED 1. 진단 한도에서 중단된 파일이 있으므로 entries는 실제 전체 항목의 정확한 총수가 아닌 하한이다. 현재 catalog 항목 100000/진단 1000, 저장 records 100000 한도와 맞지 않는다. 한도만 늘려 통과시키거나 관련 없는 번역/진단을 조용히 버리는 변경은 하지 않았다.
- 실패 분리를 위해 실제 기술 파일만 포함한 **진단 전용 별도 스냅샷**을 만들었다. 기술 정의 692개, partial 상태. 샘플 기술의 ID 검색/답변은 partial 상태를 유지하고, 원본 값 span 11개가 실제 캐시 원문과 정확히 일치했다. 선행 관계 1개는 resolved/refs ok. 번역을 제외한 진단이므로 제품 전체 색인/한영 검색/오버레이 합격을 뜻하지 않는다.
- 진단 스크립트 첫 activate 호출은 live inventory 미전달로 SOURCE_UNVERIFIED가 발생했다. sources를 전달한 정상 API 호출로 다시 실행해 위 결과를 얻었다. 제품 오류로 분류하지 않는다.

## 수행 방식

개인 .venv/real-game-acceptance-20261025 아래 별도 DB/보고서에 기록했다. 기존 load_preferences().services()를 읽고 dataclasses.replace로 data_dir만 검사 폴더로 바꿔 index_technologies를 실행했다. FileProducts와 원본 reader로 번역 항목/진단의 개수만 집계했다. 진단 전용 기술 스냅샷은 실제 기술 SourceFileInput과 adapt_technologies를 사용하고 analysis_context.scope=technology_only_diagnostic_without_localisation으로 구분했다. stage_from_results→activate(sources=실제 inventory, allow_partial=True)→SearchService/AnswerService/ReferenceService 순서로 호출했다. allow_partial은 이 별도 진단 스냅샷에만 사용했으며 원래 전체 색인의 hard-limit 실패를 우회하지 않았다.

게임 메모리·DLL/그래픽/키보드 후킹·자동 플레이·세이브 접근을 하지 않았다. 실제 원문은 저장소에 넣거나 외부로 보내지 않았다. 게임 설치는 읽기 전용으로 사용하고 원문·번역·DB·개인 경로는 공개 근거에 포함하지 않았다. 제품 코드는 수정하지 않았다. 커밋/푸시/PR/병합/배포도 실행하지 않았다.

## 남은 수용과 수정 방향

computer-use 26.1021.22027의 sky 초기화가 sandbox ACL 오류(helper_sandbox_lock_failed / SetNamedSecurityInfoW 5)로 실패했다. 제공된 cua.getApp 경로도 2회 같은 오류로 실패했다. Windows 보안 설정/권한 변경이나 별도 입력 주입으로 우회하지 않았다. 실제 게임 단축키/클릭·키 입력 통과/이동·투명도·최소화·종료는 not_run이다. 게임 창 식별만으로 이를 통과시키지 않는다.

우선 수정 대상은 실설치 번역 규모와 현재 색인 범위·안전 한도의 충돌이다. 기술 조회에 필요한 번역 및 정적 참조 closure만 투영하는 설계와, 원문 전체/중복/출처/삭제 비교의 기존 계약을 함께 정해야 한다. 이는 단순한 테스트 수정이나 무조건적인 한도 상향으로 처리하지 않는다. E-046/E-048은 not_run, TASK-033은 doing을 유지하고 이 실패 근거를 연결한다.
