# TASK-032 Main integration gate

## 목적

stacked branch/PR에 존재하던 TASK-001~003과 TASK-031 remediation을 실제 `main`에 통합했는지 별도로 추적한다.

## 현재 상태

- status: doing
- target: main
- review/integration base SHA: `1259304ff471c11bf4b8c7e151154a114db223bb`
- integration PR: #5
- merge commit: pending

## 완료 조건

1. PR #5 head가 Linux/Windows CI를 통과한다.
2. PR #5가 main에 실제 병합된다.
3. GitHub가 반환한 실제 merge commit SHA를 state/evidence에 기록한다.
4. 병합된 main에서 필수 CI 상태를 확인한다.
5. E-049를 pass, TASK-032를 done으로 바꾼 뒤에만 TASK-004를 actionable로 만든다.

PR이 열렸거나 stacked PR이 각자의 base에 merge됐다는 사실만으로 main 통합 완료로 간주하지 않는다.
