# TASK-031 generator containment follow-up evidence

날짜: 2026-09-22  
검토 기준 main: `f45f4291c5fda08f2df6ff2d42c7532857fa5b99`  
후속 PR: https://github.com/Gandalem/stellaris-suppoter/pull/7  
검증 candidate: `a5f3ca88c6b6b94e975a881e58bdfacac4db3883`

## 추가 반례

PR #6 merge 이후 리뷰에서 main 생성기의 다음 네 가지 실패가 재현됐다.

1. `output/corpus/...` 내부 디렉터리 symlink를 따라 output 밖 파일을 변경할 수 있음.
2. tampered manifest가 `README.md`를 managed path로 추가해 corpus 밖 사용자 파일을 삭제할 수 있음.
3. 이전 manifest에서 빠진 파일이 새 generated path와 충돌하면 unmanaged file을 덮어씀.
4. managed 대상이 아닌 empty directory를 cleanup 과정에서 삭제함.

기존 TASK-031 성공 evidence는 삭제하지 않는다. 이 문서는 그 뒤 발견된 반례와 후속 검증을 추가한다.

## 수정

- managed fixture path를 `corpus/` 아래로 제한.
- managed target의 각 path component에서 symlink traversal 거부.
- manifest + ownership marker로 기존 output ownership 검증.
- generated path와 unmanaged existing file 충돌 시 fail closed.
- unmanaged directory cleanup 제거.
- payload를 sibling temporary staging directory에 먼저 생성.
- 검증된 managed file만 `os.replace()`로 교체.
- main의 dangerous output root 거부 및 ownership marker 정책 유지.

## 회귀 테스트

기존 11개 synthetic corpus 테스트에 리뷰 반례 4개를 추가해 총 15개 synthetic corpus 테스트가 실행됐다.

- internal symlink escape → 외부 sentinel 유지, generator 실패.
- manifest path outside corpus → README 유지, generator 실패.
- unmanaged generated-path collision → sentinel 유지, generator 실패.
- unmanaged empty directory → force refresh 후 디렉터리 유지.

기존 unowned output force 거부, unmanaged README 보존, output 자체 symlink 거부도 계속 실행된다.

## CI

Package and tooling run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35740873031

| 환경 | job | Python | pytest | synthetic corpus | Ruff | harness |
|---|---:|---:|---|---|---|---|
| ubuntu-latest | 106789976598 | 3.11.16 | 56 passed | 15 passed | success | success |
| windows-latest | 106789977009 | 3.13.15 | 56 passed | 15 passed | success | success |

Documentation harness run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35740872951  
Ubuntu/Windows 모두 success.

## 상태

E-047의 코드/회귀 검증은 pass로 갱신한다. 그러나 리뷰에서 merge 승인이 명시적으로 보류됐고 PR #7은 아직 main에 병합되지 않았으므로 TASK-031은 blocked 상태로 유지한다. 승인 후 실제 merge commit과 main push CI를 추가 기록한 다음에만 TASK-031 done / F-002 verified로 복구한다.
