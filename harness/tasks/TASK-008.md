# TASK-008 Technology adapter

## 범위

작업 ID: TASK-008  
기능: F-005 Domain adapters  
평가: E-014 Technology extraction  
브랜치: task/TASK-008-technology-adapter  
기준 main: `959e3fc669c0927ed8eddec559bef055e155f253`

## 목표

- TASK-007의 ordered AST를 입력으로 사용한다.
- synthetic technology 정의에서 entity ID를 식별한다.
- prerequisites를 원래 순서와 source span과 함께 추출한다.
- 비용/가중치/조건/효과 등 아직 의미를 확정하지 않은 표현은 raw AST/source span으로 보존한다.
- unknown node와 duplicate field를 임의로 제거하거나 마지막 값으로 덮어쓰지 않는다.
- adapter 결과에 원본 파일/byte source reference를 연결할 수 있게 한다.
- AST 자체를 domain 의미에 맞춰 변형하지 않는다.

## E-014 Technology extraction

Synthetic demo-tech fixture에서:
- expected technology ID를 추출한다.
- prerequisites occurrence/order를 보존한다.
- raw expressions와 condition structure를 손실 없이 참조한다.
- source spans/refs가 original bytes로 역추적 가능하다.
- unsupported/duplicate fields는 명시적으로 보존하거나 diagnostic으로 남기며 invented semantics가 없어야 한다.

## 상태

TASK-007 main integration 완료 후 시작.  
TASK-008 doing.  
F-005 in_progress.  
E-014 not_run.  
F-004 verified.  
latest_game_version=null.
