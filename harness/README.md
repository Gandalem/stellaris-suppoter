# 구현 하네스 사용법

이 하네스는 특정 코딩 도구의 자동 실행 시스템이 아니라, 사람과 에이전트가 같은 상태·계약·검증 근거로 작업하도록 만드는 문서와 원장입니다. 제품 기능은 아직 구현 전이며 평가는 모두 not_run입니다.

## 파일과 권위

| 파일 | 역할 |
|---|---|
| [state.json](state.json) | 현재 단계, active_task, next_task, 마지막 인계 |
| [features.json](features.json) | 20개 기능의 상태와 요구사항 링크 |
| [tasks.json](tasks.json) | 30개 작업의 의존성·수용 조건·관련 평가 |
| [evals.jsonl](evals.jsonl) | 46개 평가 시나리오의 입력·정답 조건·실행 상태 |
| [세션 기록](sessions/2026-09-22-bootstrap.md) | 실제 수행·검증·제약·다음 작업 |
| [작업](templates/task.md) / [검토](templates/review.md) / [인계](templates/session.md) | 복사해 사용하는 기록 양식 |

TASK의 docs와 acceptance는 구현 계약이고 eval_ids는 완료에 필요한 검사입니다. fixture 필드는 앞으로 만들 합성 시나리오 이름이며, 파일이 이미 존재한다는 뜻이 아닙니다. 도메인 요구사항은 [REQUIREMENTS](../docs/REQUIREMENTS.md), 구조는 [DATA_CONTRACTS](../docs/DATA_CONTRACTS.md)가 기준입니다.

## 상태 전이

기능: planned → in_progress → verified, 필요 시 blocked. 작업: todo → doing → done, 필요 시 blocked. 평가: not_run → pass 또는 fail, 실행 환경이 없으면 blocked. 재검증이 필요하면 이전 근거를 보존하고 상태를 다시 열어 둡니다.

doing은 기본 한 작업이며 state.active_task와 일치해야 합니다. 의존 작업이 done이 아니면 doing/done으로 바꾸지 않습니다. blocked에는 blocker와 해제 조건을 기록합니다. state.next_task는 실행 가능한 todo/doing 하나이며, 실행 가능한 작업이 전혀 없을 때만 null입니다.

done에는 연결 평가의 pass와 존재하는 evidence 파일이 필요합니다. verified에는 연결 작업 전부 done, 연결 평가 전부 pass, evidence가 필요합니다. 결과가 없는 상태에서는 빈 evidence와 not_run을 유지합니다. 문서가 있다는 이유만으로 제품 상태를 올리지 않습니다.

## 실행 근거

evidence는 저장소 내부의 공개 가능한 비식별 기록 파일 경로 목록입니다. 예: harness/evidence/TASK-001-run.md. 해당 파일에 commit, 환경, 명령, exit code, 결과, 제한을 적습니다. 원문·키·개인 경로를 넣지 않습니다. 파일이 존재한다는 것은 실행의 진실성을 자동 보장하지 않으므로 검토자가 내용을 확인합니다.

## 검사기

```sh
python scripts/check_harness.py
python -m unittest discover -s tests_harness -v
```

검사 범위는 JSON 형태·ID·상태·의존성 순환·참조·완료 근거의 존재·다음 작업·상대 Markdown 파일 링크입니다. 외부 URL 접속, heading anchor 검증, 제품 테스트 실행, evidence 내용의 진실성 판정은 하지 않습니다. 출력의 product_tests_executed는 false입니다.

검사기의 자체 테스트는 작은 임시 문서 저장소를 사용합니다. 게임 fixture나 실제 파서 테스트가 아닙니다. 제품 평가 runner는 TASK-018에서 구현하며 그때 실제 실행 명령을 원장/문서에 연결합니다.

## 다음 세션

[시작 프롬프트](templates/next-session.md)를 사용해 AGENTS → state → tasks → 관련 설계/평가 순으로 읽습니다. 가장 먼저 TASK-001을 수행합니다. 변경 종료 시 원장과 [세션 양식](templates/session.md)을 갱신합니다. 긴 채팅의 기억보다 저장소의 최신 원장과 실제 파일 상태를 우선합니다.
