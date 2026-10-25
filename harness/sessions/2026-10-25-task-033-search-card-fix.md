# TASK-033 — 검색 복구와 카드 수정

사용자 승인으로 검색 오류를 수정했다. 실제 코드 SNAPSHOT_NOT_READY/No active snapshot, 동일 논리 경로지만 실행 환경별 다른 파일 식별·크기·스냅샷 상태를 확인했다. 이전 실제 사용자 색인 완료 안내를 정정했다. 사용자가 실제 앱에서 색인/부분 동의 후 ‘검색 결과가 나옴’을 확인했다.

첫 실행 색인 안내·검색 활성 조건·홈 진행 표시·부분 정보 동의 재시도·오류 표시/개인 진단·실행 파일 읽기 전용 검색 진단을 추가했다. 추가 사용자 화면의 반복 고정/흰 카드 문제는 동일 정의·스냅샷 재고정 방지, 독립 창 테마, 검증된 표시 이름, 동의/백업을 거치는 중복 정리로 수정했다.

최종 desktop 20 passed, package/docs 16 passed; 겹치는 초기 desktop/retrieval 68 및 startup 19 pass 기록 보존. Ruff/wheel/Windows build, 최종 archive 44개 소스 일치, 기존 데이터 검색 종료 0/빈 저장소 예상 진단 종료 1 확인. [근거](../evidence/TASK-033-search-startup-fix.md).

최신 파일은 dist/StellarisSupporter/StellarisSupporter.exe. 사용자가 쓰는 개인 설정은 보존했고 기존 중복은 앱의 고정 카드→중복 정리에서 동의 후 백업/정리한다. 실제 최신 카드 테마·정리 및 게임 입력/DPI/모니터 수용은 남아 TASK-033 doing/E-046/E-048 not_run 유지. 커밋·푸시·PR·병합·배포 없음.
