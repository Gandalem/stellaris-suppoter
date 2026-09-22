# TASK-031 Safety remediation and main integration

## 배경

2026-09-22 review에서 TASK-002 generator와 TASK-003 configuration/doctor에 기존 CI가 다루지 못한 파일시스템 경계 반례가 재현됐다. 기존 성공 evidence는 당시 실행 사실로 보존하지만, F-002의 verified 판정은 보완 검증 전까지 in_progress로 되돌린다.

## 범위

- generator --force의 arbitrary recursive deletion 제거.
- unmanaged output 파일 보존, managed-file ownership 검증.
- symlink output 및 위험한 output root 거부.
- config path expand/resolve/read/stat 계층의 사용자 입력 오류를 structured diagnostic으로 변환.
- POSIX directory traversal(X_OK) 검사.
- public doctor payload 전체에서 보호 경로·사용자 입력 유출 방지.
- XDG empty/relative 값 무시.
- schema_version strict integer 검증.
- Linux/Windows regression.
- main 대비 전체 TASK-001~003+remediation 통합 PR 준비.

## 완료 조건

E-047과 E-048이 실제 CI에서 pass이고, 기존 전체 pytest/Ruff/harness 회귀도 성공해야 한다. TASK-004는 TASK-031 done 전에는 시작하지 않는다. main 병합 자체는 사용자 승인 대상이므로 이 작업은 통합 PR 생성까지를 완료 조건으로 하며 실제 merge commit은 병합 후 별도 기록한다.
