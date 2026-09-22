# TASK-004 Safe inventory

## 식별·범위

작업 ID: TASK-004  
제목: Safe inventory  
관련 기능 / 평가 ID: F-003, F-013 / E-005, E-006  
기준 branch: task/TASK-004-safe-inventory  
시작 main commit: 540acda774f6c2e3b29da06aff57a63ba6652719

## 구현 범위

- 허용 root 안의 regular file만 read-only inventory.
- 상대 경로, byte size, raw-byte SHA-256 기록.
- 절대 root와 시간에 독립적인 deterministic inventory content hash.
- root 자체 및 내부 symlink/reparse-point 거부.
- 허용 root 밖 scan root / traversal 거부.
- file size, total bytes, file count, directory depth limit.
- 읽기 직전 containment/link 상태 재검사와 가능한 플랫폼의 no-follow open.
- 실제 파일 작업 오류를 structured diagnostics로 반환.
- network/write/cache/DB 작업 없음.

## 수용 조건

- 동일한 파일 tree를 서로 다른 절대 root에 두어도 상대 경로와 content hash가 동일하다.
- source bytes는 scan 전후 동일하다.
- traversal 또는 symlink/reparse escape는 fail closed.
- file/total/count/depth limit 초과는 LIMIT_EXCEEDED로 실패하며 조용히 생략하지 않는다.
- inventory 결과는 deterministic path order를 사용한다.
- Ubuntu/Windows CI에서 E-005/E-006 관련 tests와 전체 회귀/Ruff/harness가 통과한다.

## 비범위

- 실제 게임 version/DLC detection(TASK-005).
- parser/index/cache/database.
- 실제 game installation local acceptance.
- archive/save/mod semantics.

## 검증 계획

```sh
python -m pytest tests/test_inventory.py -v
python -m pytest
python -m ruff check .
python scripts/check_harness.py
```


## 완료 검증

기능 검증 commit `e4f760f567c0d76b5af28d9737c413c2a2e83526`에서 Ubuntu/Python 3.11과 Windows/Python 3.13 모두 전체 70 tests, inventory 14 tests, Ruff, harness가 통과했다.

상태: done  
E-005: pass  
E-006: pass  
F-003: in_progress (TASK-005 version/DLC evidence 남음)  
F-013: in_progress (후속 safety suite 남음)  
근거: [TASK-004 evidence](../evidence/TASK-004-safe-inventory.md)


## PR #10 review follow-up

PR #10 review에서 기존 CI가 다루지 않은 오류 처리·탐색량 제한·변경 감지·중간 링크 경계가 재현되어 TASK-004를 다시 열었다.

후속 candidate `a7357dec108d6a9bc568a2315311b80d443a4671`에서 다음을 보완했다.

- `fstat()`와 `close()`의 예상 가능한 I/O 오류를 structured diagnostic으로 변환하고, close 오류가 먼저 발생한 오류를 덮어쓰지 않도록 처리.
- NUL root와 POSIX surrogateescape/non-UTF8 filename을 fail-closed diagnostic으로 처리.
- `max_entries` 방문 항목 한도를 추가하고 `scandir()`를 전체 list로 materialize하지 않고 순회 중 제한 적용.
- 파일 수 제한도 enumeration 도중 적용.
- 읽는 중 파일 증가 시 file/remaining-total budget + 1 byte 이상 읽지 않고 실패.
- 후보 수집 당시 size/mtime/inode/device identity를 보존하고 open 전 비교.
- 읽기 종료 후 열린 파일 identity뿐 아니라 경로가 여전히 같은 파일을 가리키는지 다시 확인.
- 명시적 allowed root 내부에서 scan 시작 경로의 원래 중간 구성요소를 resolve 전에 검사해 symlink/reparse traversal 거부.
- Windows에서 lstat/open identity 비교에 불안정한 `st_ctime_ns`를 사용하지 않고 size/mtime + 가능한 inode/device를 사용.

검증:
- Ubuntu/Python 3.11: 전체 81 tests, inventory 25 tests 전부 통과.
- Windows/Python 3.13: 전체 81 tests 통과, inventory 25개 중 POSIX 전용 non-UTF8 filename 1개만 의도적 skip, 나머지 통과.
- Ruff/harness 성공.
- Documentation harness Ubuntu/Windows 성공.

E-005/E-006은 follow-up candidate에서 pass로 복구했지만 TASK-004 자체는 reviewer 재검토와 main 병합 전까지 `doing`으로 유지한다.

근거: [review follow-up evidence](../evidence/TASK-004-review-followup.md)


## 실제 main 병합 완료

PR #10 head `219b41f3853406b0c069d553f9fcf635ffc715c0`는 merge commit `472aad700e24e03b20081f13b653502b673c7d00`으로 main에 반영됐다.

실제 main push CI:
- Package and tooling run 35749603679
  - Ubuntu/Python 3.11.16: 81 passed, inventory 25 passed, Ruff/harness success.
  - Windows/Python 3.13.15: 81 collected, 80 passed + POSIX-only 1 skipped; inventory 24 passed + 1 skipped, Ruff/harness success.
- Documentation harness run 35749603578: Ubuntu/Windows success.

따라서 TASK-004는 `done`으로 종료한다. E-005/E-006 pass는 유지하며 F-003/F-013은 후속 작업이 남아 `in_progress`를 유지한다.
