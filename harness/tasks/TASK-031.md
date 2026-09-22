# TASK-031 Safety remediation

## 배경

2026-09-22 review에서 TASK-002 generator와 TASK-003 configuration/doctor에 기존 CI가 다루지 못한 파일시스템 경계 반례가 재현됐다. 기존 성공 evidence는 당시 실행 사실로 보존했고, F-002를 일시적으로 in_progress로 되돌린 뒤 추가 회귀를 만들었다.

## 구현

- generator `--force` arbitrary recursive deletion 제거.
- manifest ownership 기반 managed-file-only refresh와 unmanaged file 보존.
- symlink output 및 repository/home/filesystem 위험 root 거부.
- config path expand/resolve/read/stat 계층 사용자 오류의 structured diagnostics.
- NUL path 명시 거부.
- POSIX directory traversal(`X_OK`) 진단.
- public doctor payload 전체의 code-based safe diagnostic serialization.
- XDG empty/relative 값 무시.
- schema_version strict integer 검증.
- remediation branch CI 활성화와 Linux/Windows regression.

## 검증

GitHub Actions run 35734466487:
- Ubuntu / Python 3.11.16 / job 106768029365: 55 passed, Ruff success, harness success.
- Windows / Python 3.13.15 / job 106768028931: 55 passed, Ruff success, harness success.

## 종료

상태: done  
E-047: pass  
E-048: pass  
F-002: verified 재확정  
근거: [TASK-031 evidence](../evidence/TASK-031-safety-remediation.md)

main 통합 자체는 별도 TASK-032에서 추적하며 실제 merge commit 기록 전 TASK-004를 시작하지 않는다.
