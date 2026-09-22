# TASK-031 generator containment follow-up evidence

날짜: 2026-09-22  
검토 기준 main(before): `f45f4291c5fda08f2df6ff2d42c7532857fa5b99`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/7  
reviewed head: `9f61a0a727c4c47d507b84600b18b5611e59b277`  
actual main merge commit: `b583f89de389ce838987b8c3e5b6a2fd0e7c58b9`

## 추가 반례

PR #6 merge 이후 review에서 main 생성기의 다음 네 가지 실패가 재현됐다.

1. `output/corpus/...` 내부 디렉터리 symlink를 따라 output 밖 파일을 변경할 수 있음.
2. tampered manifest가 `README.md`를 managed path로 추가해 corpus 밖 사용자 파일을 삭제할 수 있음.
3. 이전 manifest에서 빠진 파일이 새 generated path와 충돌하면 unmanaged file을 덮어씀.
4. managed 대상이 아닌 empty directory를 cleanup 과정에서 삭제함.

기존 TASK-031 성공 evidence는 삭제하지 않고, 이 문서를 후속 재검증 근거로 추가한다.

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

리뷰에서 실패한 네 사례를 기존 synthetic corpus 테스트에 추가했다.

- internal symlink escape → 외부 sentinel 유지, generator 실패.
- manifest path outside corpus → README 유지, generator 실패.
- unmanaged generated-path collision → sentinel 유지, generator 실패.
- unmanaged empty directory → force refresh 후 디렉터리 유지.

기존 unowned output force 거부, unmanaged README 보존, output 자체 symlink 거부도 계속 실행된다. Reviewer의 독립 재검사에서는 manifest symlink, ownership-marker symlink, managed leaf-file symlink도 거부되고 거부 전후 filesystem state가 유지됨을 확인했다.

## PR candidate CI

Package and tooling run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35741212839

| 환경 | job | Python | pytest | synthetic corpus | Ruff | harness |
|---|---:|---:|---|---|---|---|
| ubuntu-latest | 106791157588 | 3.11.16 | 56 passed | 15 passed | success | success |
| windows-latest | 106791157298 | 3.13.15 | 56 passed | 15 passed | success | success |

Documentation harness run 35741212835도 Ubuntu/Windows 모두 success.

## 실제 main merge 검증

PR #7은 2026-09-22 23:43:06 KST에 merge되었고 실제 merge commit은 `b583f89de389ce838987b8c3e5b6a2fd0e7c58b9`이다.

Main push Package and tooling run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35742263578

| 환경 | job | Python | pytest | synthetic corpus | Ruff | harness |
|---|---:|---:|---|---|---|---|
| windows-latest | 106794770824 | 3.13.15 | 56 passed | 15 passed | success | success |
| ubuntu-latest | 106794771348 | 3.11.16 | 56 passed | 15 passed | success | success |

Main push Documentation harness run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35742263716  
Ubuntu/Windows 모두 success.

## 최종 상태

E-047=pass, TASK-031=done, F-002=verified. TASK-004 Safe inventory dependency가 충족됐다.

## 비차단 후속

`manifest.json`의 top-level 값이 object가 아닌 list/null/string인 손상 입력은 명시적인 ValueError/exit 2로 정규화하는 후속 보완이 필요하다. 현재 재현에서는 traceback이 발생하지만 파일 변경은 없었으므로 이번 containment merge의 차단 사유로는 취급하지 않았다.
