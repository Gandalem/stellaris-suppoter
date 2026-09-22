# TASK-031 safety remediation evidence

날짜: 2026-09-22  
리뷰 기준 원본 TASK-003 commit: `1dba5d85addc0c27d96c41c067120fffb056c5e6`  
보완 코드 검증 commit: `b6542944562d00085727494e8d8e3b64dcc954af`  
GitHub Actions: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35734466487

## 리뷰에서 재현된 문제와 보완

### Synthetic generator

기존 `--force`의 output 전체 `rmtree`를 제거했다. 비어 있지 않은 output은 기존 `manifest.json`이 `origin=synthetic`, 프로젝트 generator 식별자, managed file 목록을 제공할 때만 refresh한다. refresh는 기존/새 managed file만 교체하고 unmanaged file을 보존한다.

출력 자체가 symlink인 경우, repository root, user home, filesystem root는 거부한다. managed 경로 내부의 symlink 및 unmanaged collision도 거부한다. 테스트는 user README 보존, tampered managed file 복구, unowned directory force 거부, symlink target 보존, repository root 보존을 확인한다.

### Configuration and doctor

- NUL path를 OS 동작에 맡기지 않고 명시적으로 invalid 처리.
- home expression/path resolve 실패를 structured diagnostic으로 변환.
- config read/stat permission 오류를 structured diagnostic으로 변환.
- XDG_CONFIG_HOME/XDG_DATA_HOME empty 또는 relative 값은 무시하고 기본값 사용.
- `schema_version = 1.0`은 integer 1이 아니므로 거부.
- POSIX game directory는 `R_OK|X_OK`, data directory는 `R_OK|W_OK|X_OK`를 진단.
- `os.access`는 실제 I/O 성공 보장이 아니므로 후속 inventory가 실제 작업 예외를 처리해야 함을 문서화.
- public doctor report는 settings path placeholder뿐 아니라 diagnostics message도 code 기반 정적 공개 문구로 변환.
- 전체 public JSON 문자열에서 synthetic private path marker가 사라지는지 테스트.

Linux와 Windows의 `~user` 해석 차이도 확인했다. Linux에서 resolve 오류가 될 수 있고 Windows에서는 사용자 디렉터리 경로로 해석된 뒤 missing이 될 수 있으므로 둘 다 structured failure로 취급한다.

## 실제 실행

| 환경 | job | Python | pytest | Ruff | harness |
|---|---:|---:|---|---|---|
| ubuntu-latest | 106768029365 | 3.11.16 | 55 passed | success | success |
| windows-latest | 106768028931 | 3.13.15 | 55 passed | success | success |

양쪽 모두 editable install, pip check, package import, CLI help/version도 success였다. harness 결과는 31 tasks / 48 evaluations 상태에서 valid였다.

## 중간 실패 보존

- run 35734050858: 기존 Linux test가 game access mode를 정확히 R_OK로 고정해 새 X_OK 계약과 충돌.
- run 35734141534: Windows에서 NUL resolve semantics 차이 노출.
- run 35734314435: Windows `~user`가 Linux와 달리 missing user path로 해석되는 차이 노출.
- 각 원인을 계약에 맞게 교정한 후 run 35734466487에서 양 플랫폼 전체 통과.

## 외부 기술 근거

XDG empty/relative 처리 기준은 freedesktop XDG Base Directory Specification 0.8을 확인했다. Python 3.13 os 문서는 `R_OK/W_OK/X_OK`와 `os.access` 사전 검사보다 실제 I/O 예외 처리(EAFP)를 권장하고, access 성공이어도 실제 I/O가 실패할 수 있음을 명시한다. 저장소의 [S-12/S-13](../../docs/SOURCES.md)에 기록했다.

## 통합 상태

리뷰 당시 및 PR 생성 직전 main은 `1259304ff471c11bf4b8c7e151154a114db223bb`였다. main 대상 통합 PR은 #5이며 자동 병합하지 않는다. 실제 merge commit은 TASK-032에서 기록한다. 따라서 이 evidence는 안전성 보완 완료의 근거이지 main 통합 완료의 근거가 아니다.
