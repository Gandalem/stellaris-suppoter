# 문서 지도

작성 기준일: 2026-09-22. 이 묶음은 **앞으로 구현할 제품의 명세와 개발 하네스**입니다. 현재 구현된 것은 원장 검사기와 그 자체 테스트뿐입니다.

## 사용자·제품 담당자

| 문서 | 답하는 질문 |
|---|---|
| [제품 정의](PRODUCT.md) | 무엇을 만들며 첫 버전은 어디까지인가? |
| [요구사항](REQUIREMENTS.md) | 기능마다 무엇이 성공·실패인가? |
| [환경 준비](ENVIRONMENT.md) | 지금 필요한 것, 나중에 필요한 것, 아직 확인할 것은? |
| [로드맵](ROADMAP.md) | 최소 제품에서 AI 참모까지 어떤 순서인가? |
| [작업 목록](BACKLOG.md) | 다음으로 정확히 무엇을 구현하는가? |

## 구현 담당자

| 문서 | 책임 |
|---|---|
| [AGENTS](../AGENTS.md) / [기여 안내](../CONTRIBUTING.md) | 세션·변경·검토 규칙 |
| [아키텍처](ARCHITECTURE.md) | 모듈 경계, 데이터 흐름, 오류 처리 |
| [데이터 계약](DATA_CONTRACTS.md) | 스냅샷·출처·AST·엔티티·답변 구조 |
| [파싱과 현지화](PARSING.md) | 지원 구문, 보존 규칙, 번역 연결 |
| [검색과 근거](SEARCH_AND_ANSWERS.md) | 한국어 검색, 출처, 답변 보류 |
| [CLI 계약](CLI.md) | 명령, 출력, 오류 코드 |
| [업데이트와 버전](UPDATES.md) | 설치 데이터·정식 공지·베타 분리 |
| [테스트 전략](TESTING.md) / [평가](EVALUATION.md) | 재현, 회귀, 계량 기준 |
| [운영·복구](OPERATIONS.md) / [릴리스](RELEASE.md) | 실패 복구, 배포 게이트 |
| [보안](../SECURITY.md) | 권한, 공개 데이터, 모델·네트워크 경계 |
| [결정 기록](DECISIONS.md) | 선택 이유와 변경 조건 |
| [불확실성](UNKNOWNS.md) / [출처](SOURCES.md) | 확인되지 않은 사실과 검증 근거 |

## 기계 판독 하네스

[사용법](../harness/README.md) → [상태](../harness/state.json) → [작업](../harness/tasks.json) → [기능](../harness/features.json) → [평가 사례](../harness/evals.jsonl).

[작업 명세](../harness/templates/task.md), [세션 기록](../harness/templates/session.md), [검토](../harness/templates/review.md), [다음 세션 프롬프트](../harness/templates/next-session.md)를 복사해 사용합니다. 최초 기록은 [문서 부트스트랩](../harness/sessions/2026-09-22-bootstrap.md)입니다.

## 문서 사용 원칙

본문의 `MUST` 또는 '필수'는 릴리스 조건, '설계 선택'은 변경 가능한 초기 결정, '후속'은 현재 범위 밖입니다. 예시 수치·가상 기술은 실제 게임 정보가 아닙니다. 작업 상태를 문서 여러 곳에 수동 복사하지 않습니다. 설치 경로·버전·사용자 환경이 없는 자리는 추측 대신 명시적 미확인 상태로 유지합니다.
