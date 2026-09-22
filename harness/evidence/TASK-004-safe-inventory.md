# TASK-004 safe inventory evidence

날짜: 2026-09-23  
기능 검증 commit: `e4f760f567c0d76b5af28d9737c413c2a2e83526`  
GitHub Actions run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35744608339

## 구현

- 허용 root 안 regular files만 inventory.
- relative POSIX path, byte size, raw-byte SHA-256 기록.
- 절대 root와 시간에 독립적인 deterministic content hash.
- root 및 내부 symbolic link / Windows reparse point 거부.
- allowed root 밖 scan root 거부.
- file byte / total byte / file count / directory depth 한도.
- 후보 수집 뒤 실제 open 직전에 lstat/resolve containment 재검사.
- 플랫폼이 제공하면 O_NOFOLLOW 사용.
- os.open은 read-only flags만 사용.
- open/fstat/read 중 변경 또는 오류를 SOURCE_CHANGED / FILESYSTEM_ERROR 등 structured diagnostic으로 실패 처리.
- source tree, network, cache, DB에 write 없음.

## E-005 deterministic inventory

합성 tree를 서로 다른 두 절대 root에 동일 bytes로 생성해 다음을 검증했다.

- relative paths와 file records 동일.
- content_hash 동일.
- 파일 순서는 relative path 기준 결정적.
- scan 전후 source bytes 동일.
- 동일 bytes라도 relative path가 다르면 content_hash가 달라짐.
- empty inventory hash도 절대 root에 독립적.

## E-006 filesystem containment

- scan root가 allowed root 밖이면 PATH_REJECTED.
- root directory symlink 거부.
- 내부 directory symlink escape 거부.
- leaf file symlink escape 거부.
- Windows reparse attribute를 link boundary로 취급.
- file_bytes, total_bytes, max_files, max_depth 초과는 LIMIT_EXCEEDED.
- synthetic PermissionError on open은 traceback 대신 FILESYSTEM_ERROR.
- 거부/실패 사례에서 source sentinel bytes는 유지.

## 실제 CI

| 환경 | job | Python | 전체 pytest | inventory tests | Ruff | harness |
|---|---:|---:|---:|---:|---|---|
| ubuntu-latest | 106802842156 | 3.11.16 | 70 passed | 14 passed | success | success |
| windows-latest | 106802841860 | 3.13.15 | 70 passed | 14 passed | success | success |

두 환경 모두 install, pip check, import, CLI help/version도 success였다.

## 한계

이 검증은 synthetic/temp filesystem만 사용했다. 실제 Stellaris 설치, version/DLC, mods는 읽지 않았다. TOCTOU race를 완전히 제거한다고 주장하지 않으며 scanner가 open 직전 재검사와 가능한 O_NOFOLLOW로 위험을 줄이는 수준이다. 실제 게임 설치 acceptance는 TASK-021에서 별도로 수행한다.
