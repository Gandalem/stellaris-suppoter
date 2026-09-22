# 2026-09-23 TASK-004 PR #10 review follow-up

사용자 리뷰에서 PR #10 head `aea10e2`의 기존 70-test CI 밖에서 7개 추가 실패가 재현됐다는 피드백을 받았다.

## 수행

- TASK-004/E-005/E-006을 재검증 상태로 재개방.
- fstat/close/path encoding/NUL 오류 처리 보강.
- streaming scandir + max_entries 방문 한도 추가.
- read budget을 remaining total/file limit에 연결.
- candidate identity에 size/mtime/inode/device 저장.
- open 전/후, read 종료 후 descriptor/path identity 재검증.
- allowed root 내부 scan 시작 경로 중간 link component 검사 추가.
- 새 회귀 테스트 추가.

Windows 첫 run에서 ctime 기반 identity가 정상 파일을 SOURCE_CHANGED로 오판하는 차이를 발견했고, ctime을 동일성 키에서 제외한 뒤 재실행했다.

## 검증

Candidate `a7357dec108d6a9bc568a2315311b80d443a4671`:
- Ubuntu: 81 passed, inventory 25 passed, Ruff/harness success.
- Windows: 81 passed; inventory 24 passed + POSIX-only filename regression 1 skipped; Ruff/harness success.
- Documentation harness: Ubuntu/Windows success.

## 인계

E-005/E-006 pass로 복구. TASK-004는 reviewer 재검토/merge 승인 전까지 doing. TASK-005는 시작하지 않는다.
