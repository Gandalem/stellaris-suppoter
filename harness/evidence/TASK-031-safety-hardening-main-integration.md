# TASK-031 safety hardening and main integration evidence

날짜: 2026-09-22  
검증 commit: `b6189f8adf7ebc8c344293bacd51cadc67b14bf0`  
main 기준점: `1259304ff471c11bf4b8c7e151154a114db223bb`  
integration PR: https://github.com/Gandalem/stellaris-suppoter/pull/6

## 리뷰 반례 대응

- generator `--force`: 임의 폴더 전체 삭제 제거.
- ownership marker와 이전 manifest에 기록된 관리 파일만 삭제·교체.
- generator symlink output 거부.
- filesystem root, repository root 및 repository 상위 경로를 output으로 거부.
- generator-owned output에 추가된 사용자 파일은 `--force` 뒤에도 보존.
- config path/path value의 NUL 및 지원하지 않는 named-user expansion을 filesystem 호출 전에 차단.
- path resolve/status/access 실패를 structured diagnostic으로 변환.
- POSIX game directory는 R_OK|X_OK, data directory는 R_OK|W_OK|X_OK 검사.
- 실제 I/O 성공을 os.access 결과로 보장한다고 주장하지 않음; TASK-004 이후 작업 시점 오류 처리는 별도 필요.
- public doctor report는 settings뿐 아니라 diagnostic message/remediation도 user-derived 내용이 노출되지 않는 형태로 직렬화.
- empty/relative XDG_CONFIG_HOME/XDG_DATA_HOME 무시.
- schema_version은 정확한 int 1만 허용.

## 통합 계보

`fix/safety-hardening-main-integration`은 main commit `1259304...`에서 직접 분기했다. commit `61809b9...`가 TASK-003 완료 tree를 main의 직접 자식으로 통합했고, 이후 안전성 수정 커밋을 쌓았다. 따라서 PR #6은 stacked branch가 아니라 `main` 자체를 대상으로 한다.

## 최종 검증

Package and tooling PR run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35738142800

| 환경 | job | Python | pytest | Ruff | harness |
|---|---:|---:|---|---|---|
| ubuntu-latest | 106780581633 | 3.11.16 | 52 passed | success | success |
| windows-latest | 106780582100 | 3.13.15 | 52 passed | success | success |

Documentation harness run 35738142796도 Ubuntu/Windows 모두 success.

초기 PR run에서는 NUL 테스트가 subprocess argv 경계에서 애플리케이션 실행 전에 실패했고, 다음 run에서는 Windows의 `~user`/NUL Path 동작 차이를 발견했다. 테스트 재현 경계를 수정하고 플랫폼 독립 정책을 명시적으로 구현한 뒤 위 최종 run에서 양 플랫폼 모두 통과했다.

## 한계

이 evidence는 리뷰에서 제기된 안전성 반례와 main-line 통합 준비를 검증한다. 실제 권한 race/TOCTOU를 제거한다는 뜻이 아니며, 실제 inventory의 open/stat 오류 처리는 TASK-004에서 계속 처리해야 한다. 실제 Stellaris 설치 파일은 사용하지 않았다.
