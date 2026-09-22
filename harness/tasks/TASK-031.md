# TASK-031 Safety hardening and main integration

상태: done  
평가: E-047 pass  
근거: [TASK-031 evidence](../evidence/TASK-031-safety-hardening-main-integration.md)

Post-TASK-003 review에서 재현된 filesystem/integration 반례를 수정했다. Generator managed-only replacement, path exception diagnostics, POSIX traversal access, public-report redaction, XDG validation, strict schema version을 Linux/Windows에서 재검증했다.

통합 브랜치는 main에서 직접 분기했으며 PR #6이 main을 대상으로 한다. 실제 merge commit은 PR 병합 후 이 문서/후속 세션에서 추적한다.

TASK-004는 TASK-031에 의존하며 현재 dependency가 충족됐다.


## Post-merge review reopening

After the first TASK-031 completion and PR #6 merge, review reproduced four additional generator containment failures on main: an internal symlink escape, manifest ownership expansion outside `corpus/`, overwrite of an unmanaged colliding file, and deletion of an unmanaged empty directory. The prior CI/evidence remains historical evidence, but TASK-031 and E-047 are reopened until these cases pass on the final integration SHA.


## Generator containment follow-up

PR #6 병합 후 추가 리뷰에서 내부 symlink escape, manifest ownership expansion, unmanaged collision overwrite, unmanaged empty-directory deletion이 재현됐다. PR #7 candidate `a5f3ca88c6b6b94e975a881e58bdfacac4db3883`에서 네 사례를 회귀 테스트로 추가했고 Ubuntu/Windows에서 56 tests, synthetic corpus 15 tests, Ruff, harness가 모두 통과했다.

E-047은 새 candidate 검증으로 pass지만, merge 승인이 명시적으로 보류된 상태이므로 TASK-031은 `blocked`로 유지한다. 실제 main merge commit과 main push CI를 기록한 후에만 done으로 복구한다.

근거: [generator containment follow-up](../evidence/TASK-031-generator-containment-followup.md)
