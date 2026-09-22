# TASK-031 Safety hardening and main integration

상태: done  
평가: E-047 pass  
최종 main merge commit: `b583f89de389ce838987b8c3e5b6a2fd0e7c58b9`  
근거:
- [initial safety hardening](../evidence/TASK-031-safety-hardening-main-integration.md)
- [generator containment follow-up](../evidence/TASK-031-generator-containment-followup.md)

## 완료 범위

Post-TASK-003 review에서 재현된 configuration/doctor 경계 문제와 synthetic corpus generator의 파일 보호 문제를 수정했다.

- generator의 임의 디렉터리 전체 삭제 제거.
- generator ownership marker와 manifest 기반 managed-file 교체.
- output 자체 및 managed path 구성요소의 symlink escape 거부.
- managed fixture path를 `corpus/` 아래로 제한.
- unmanaged generated-path collision overwrite 거부.
- unmanaged file/empty directory 보존.
- staging 후 검증된 managed file만 교체.
- path resolution/status 오류 structured diagnostics.
- POSIX directory traversal 권한 검사.
- public doctor report 전체 redaction.
- XDG empty/relative 값 fallback.
- strict integer `schema_version = 1`.

## 검증 흐름

첫 TASK-031 검증 이후 PR #6이 main에 병합됐지만, 추가 review가 generator containment 반례 4개를 재현해 작업을 재개방했다. PR #5의 관련 방어 로직을 현재 main에 필요한 범위만 선별 통합해 PR #7을 만들고 새 회귀 테스트를 추가했다.

PR #7 reviewed head:
`9f61a0a727c4c47d507b84600b18b5611e59b277`

실제 main merge:
`b583f89de389ce838987b8c3e5b6a2fd0e7c58b9`

Main push CI:
- Package and tooling run 35742263578: Ubuntu/Windows success, 양쪽 56 tests, synthetic corpus 15 tests, Ruff/harness success.
- Documentation harness run 35742263716: Ubuntu/Windows success.

따라서 TASK-031=done, E-047=pass, F-002=verified로 최종 복구한다. TASK-004 dependency는 충족됐다.

## 비차단 후속

정상 ownership marker가 존재하는 상태에서 `manifest.json`이 JSON object가 아닌 list/null/string이면 현재 `data.get()`에서 내부 예외가 발생할 수 있다. 재검토에서는 파일 변경 없이 중단되는 것을 확인했으므로 TASK-031 merge blocker로 보지 않았지만, generator가 명시적 오류와 exit 2를 반환하도록 후속 보완해야 한다.
