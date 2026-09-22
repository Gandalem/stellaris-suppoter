# TASK-004 PR #10 review follow-up evidence

날짜: 2026-09-23  
리뷰 전 head: `aea10e20b8b45a361c95ce7582deb000eefc927d`  
후속 기능 candidate: `a7357dec108d6a9bc568a2315311b80d443a4671`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/10

## 추가 리뷰에서 재현된 영역

기존 TASK-004 성공 기록은 삭제하지 않는다. PR #10 추가 검토에서 다음 범위의 누락 사례가 재현되어 이 follow-up을 추가했다.

1. `os.fstat()`, `os.close()`, NUL root, POSIX non-UTF8 filename 오류 경계.
2. `scandir()` 전체 materialization과 파일 수 외 방문 항목 한도 부재.
3. 읽는 중 파일 성장 시 실제 read 양이 총량 정책보다 크게 진행될 수 있는 문제.
4. 후보 수집 뒤 same-size 변경과 read 도중 path replacement 감지 부족.
5. 명시적 allowed root 내부의 scan 시작 경로 중간 symlink traversal.

## 수정

### 오류 경계

- lstat/scandir/path resolution의 예상 가능한 OSError/RuntimeError/ValueError를 structured diagnostics로 변환.
- descriptor `fstat()`는 `FILESYSTEM_ERROR`로 변환.
- descriptor `close()` 실패도 `FILESYSTEM_ERROR`로 변환하되 이미 처리 중인 primary failure가 있으면 close failure가 이를 덮어쓰지 않음.
- NUL root는 raw exception 대신 diagnostic.
- POSIX surrogateescape filename은 조용히 변환하거나 누락하지 않고 `PATH_REJECTED`.

### 자원 한도

- `Limits.max_entries` 기본값 100,000 추가.
- `os.scandir()` 결과를 `list()`로 전부 올리지 않고 streaming enumeration 중 `max_files`와 `max_entries` 적용.
- 성공 출력은 수집 후 relative path 정렬로 결정성 유지.
- file read request는 `min(file_bytes, remaining total_bytes) + 1` 이상 요청하지 않음. 한도 초과 감지는 한 바이트의 sentinel read까지만 허용.

### 변경 감지

후보 수집 때 size, mtime_ns, 가능한 inode/device identity를 저장한다.
- open 전 현재 path 상태와 후보 identity 비교.
- open 후 descriptor identity 비교.
- read 종료 후 descriptor identity 재검사.
- read 종료 후 path 자체를 다시 lstat/containment 검사하고 열린 file identity와 비교.

Windows에서 lstat와 opened descriptor 사이 `st_ctime_ns`가 동일성 키로 안정적이지 않은 사례가 CI에서 발견되어 ctime은 identity 키에서 제외했다.

### 시작 경로 링크

명시적 `allowed_root`를 신뢰 경계로 두고, `root`의 lexical path를 allowed root 기준으로 계산한 뒤 각 내부 구성요소를 resolve 전에 lstat하여 symlink/reparse point를 거부한다. 이후 resolved path도 allowed root containment를 다시 확인한다.

## 회귀 테스트

기존 inventory 14개에 리뷰 follow-up 테스트를 추가하여 총 25개 inventory tests가 수집된다.

추가 coverage:
- 첫/둘째 fstat 오류.
- close 오류.
- NUL root.
- POSIX non-UTF8 filename.
- max_files=1에서 2,000개 파일을 전부 enumerate하지 않고 조기 실패.
- 2,000개 empty directory에서 `max_entries`로 bounded traversal.
- 읽는 중 파일 성장 시 작은 total budget을 넘는 대량 read 방지.
- enumeration 뒤 same-size content+mtime 변경 감지.
- read 종료 시 path identity replacement 감지.
- allowed root 내부 intermediate symlink scan start 거부.

## CI

Package and tooling PR run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35748136179

| 환경 | job | 전체 pytest | inventory | Ruff | harness |
|---|---:|---:|---:|---|---|
| Ubuntu / Python 3.11 | 106814936925 | 81 passed | 25 passed | success | success |
| Windows / Python 3.13 | 106814936643 | 80 passed + 1 POSIX-only skip (81 collected) | 24 passed + 1 POSIX-only skip | success | success |

Windows skip:
`test_inventory_rejects_non_utf8_filename_as_structured_diagnostic`은 surrogateescape filename을 직접 만드는 POSIX 전용 regression이다. Windows에서 같은 filename representation을 지원한다고 주장하지 않는다.

Documentation harness run 35748136285도 Ubuntu/Windows 모두 success.

## 상태

E-005/E-006은 follow-up candidate에서 pass. TASK-004는 기술 검증만으로 완료 처리하지 않고 reviewer 재검토 및 실제 main 병합 전까지 `doing`으로 유지한다. TASK-005는 아직 시작하지 않는다.


## 실제 main 통합

PR #10 merge commit: `472aad700e24e03b20081f13b653502b673c7d00`

Main push run 35749603679:
- Ubuntu/Python 3.11.16: 81 passed; inventory 25 passed; Ruff/harness success.
- Windows/Python 3.13.15: 81 collected, 80 passed + POSIX-only 1 skipped; inventory 24 passed + 1 skipped; Ruff/harness success.

Documentation harness run 35749603578도 Ubuntu/Windows 모두 success였다. 이 실제 main evidence로 TASK-004 종료 조건이 충족됐다.
