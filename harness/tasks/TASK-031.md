# TASK-031 Safety hardening and main integration

상태: done  
평가: E-047 pass  
근거: [TASK-031 evidence](../evidence/TASK-031-safety-hardening-main-integration.md)

Post-TASK-003 review에서 재현된 filesystem/integration 반례를 수정했다. Generator managed-only replacement, path exception diagnostics, POSIX traversal access, public-report redaction, XDG validation, strict schema version을 Linux/Windows에서 재검증했다.

통합 브랜치는 main에서 직접 분기했으며 PR #6이 main을 대상으로 한다. 실제 merge commit은 PR 병합 후 이 문서/후속 세션에서 추적한다.

TASK-004는 TASK-031에 의존하며 현재 dependency가 충족됐다.
