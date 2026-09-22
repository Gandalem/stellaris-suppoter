# 구현 작업 목록

상태·의존성·연결 평가는 [tasks.json](../harness/tasks.json)이 단일 원장입니다. 아래는 각 작업의 구현 산출물과 수용 조건입니다. 최초 작업은 TASK-001이며 제품 작업은 아직 시작하지 않았습니다. 한 작업이 너무 크면 하위 작업 ID와 의존성을 추가하고 기존 ID를 재사용하지 않습니다.

## M1: 첫 수직 슬라이스

| 작업 | 구현할 산출물 | 수용 조건 |
|---|---|---|
| TASK-001 | pyproject, src 패키지, dev 도구·초기 CI | 깨끗한 환경에서 설치·import·help·테스트; 구현 전 스텁을 기능 완료로 오해하지 않음 |
| TASK-002 | 합성 corpus와 생성/정답 문서 | 실제 게임 원문 없음; 정상·오류·번역·충돌 시나리오 재현 가능 |
| TASK-003 | TOML 설정, 경로 정책, doctor 서비스 | 오류 경로와 data/game 겹침 거부; network off; runtime 기능 진단 |
| TASK-031 | 리뷰 안전성 보완 | generator 삭제 경계, adversarial path/permission, public redaction, XDG/schema 회귀 검증 |
| TASK-032 | main 통합 게이트 | main 대상 PR·양 플랫폼 CI·실제 merge commit 기록 전 TASK-004 차단 |
| TASK-004 | 안전한 inventory와 content hash | 상대 경로·해시 안정성, root 탈출·한도 방어, 원본 무변경 |
| TASK-005 | 버전·분기·DLC 증거 모델 | metadata/user_reported/unknown 구별; 설치·소유·활성을 혼동하지 않음 |
| TASK-006 | lexer와 source span | 문자열·주석·escape·BOM/CRLF·연산자의 원문 위치 일치 |
| TASK-007 | 순서 보존 AST와 오류 복구 | 중복·혼합 블록 보존, 미지원 구문 진단, 깊이 제한 |
| TASK-008 | 기술 adapter | demo 기술의 ID·필드·조건·선행 참조·원문 위치 추출 |
| TASK-009 | 현지화 reader와 resolver | 한글/영어/ID fallback, 누락·중복·순환·동적 표현식 처리 |
| TASK-010 | SQLite schema/types, snapshot 저장 | 계약 일치, 동일 입력 결정성, staging 실패 시 active 보존 |
| TASK-011 | 검색기 | ID·이름·별칭·두 글자 한국어·안전한 특수문자 검색 |
| TASK-012 | 정적 답변·인용 formatter | 모든 facts에 실제 span, unsupported/not_found 처리, 버전 분리 |
| TASK-013 | CLI 수직 통합 | fixture → index → search/show/JSON, 명령·종료 코드·로그 분리 |

## M2~M3: 신뢰 가능한 v0.1

| 작업 | 구현할 산출물 | 수용 조건 |
|---|---|---|
| TASK-014 | 부품·건물·지구·직업·특성·정부/시빅/기원·전통·승천·이벤트 adapter | 각 범주 합성 정상/오류/충돌/번역 사례, 범주별 지원 상태 |
| TASK-015 | 정적 참조 그래프·refs | 누락·동명·순환·깊이 제한, 실제 실행과 구별 |
| TASK-016 | 증분 index·snapshot diff | 추가·변경·삭제·정책 변경과 수집 중 변경 처리, 이전 active 보존 |
| TASK-017 | 안전·개인정보 통합 회귀 | 무단 통신·원본 쓰기·개인 경로/키 노출·입력 지시 실행 0건 |
| TASK-018 | 평가 runner와 정답 corpus | E-ID와 재현 명령 연결, 최소 40 검색 질의, 결과/근거 파일 생성 |
| TASK-019 | 성능 fixture·benchmark 기록 | 10,000 엔티티, 환경·cold/warm·p95 기록; 미측정 수치 주장 없음 |
| TASK-020 | wheel·설치 문서·CI matrix | 깨끗한 Linux/Windows 설치 스모크; OS별 실제 실행 여부 기록 |
| TASK-021 | 사용자 로컬 read-only 검증 보고 | 실제 경로·구문·도메인 coverage·한계 확인; 비공개 원문 노출 없음 |
| TASK-022 | v0.1 릴리스 체크리스트·변경 기록 | 모든 필수 게이트와 지원 범위, 롤백·설치 안내; 배포는 별도 승인 |

TASK-021은 사용자 설치 환경이 있어야 실행할 수 있습니다. 없으면 해당 작업만 blocked로 두고 preview와 이미 실행한 합성 검증을 구별합니다. TASK-022는 라이선스·릴리스 승인 문제가 해결되지 않으면 배포하지 않습니다.

## M4 이후: 시작할 때 세분화

| 작업 | 구현 방향 | 필수 검증 |
|---|---|---|
| TASK-023 | 공식 공지 수집·최신성 캐시 | 날짜/채널/플랫폼/버전 분리, timeout·429·오프라인 표시 |
| TASK-024 | 선택적 LLM provider·EvidencePacket | provider none fallback, 모델/전송 동의, 예산·timeout |
| TASK-025 | 모델 근거·안전 평가 | 가짜 인용·수치·주입 지시 차단, 정적 출력 복귀 |
| TASK-026 | 모드 목록·순서 조사 | 설치/활성/로드순서 증거 구분, 불명 상태 보존 |
| TASK-027 | 범주별 모드 적용 resolver | replace_path·파일/객체 충돌 검증, unresolved를 실제 적용이라고 표시하지 않음 |
| TASK-028 | 세이브 reader | 형식·버전·압축 한도·필드 의미 검증, 읽기 전용 |
| TASK-029 | 경제·전투 계산기 | 수식·단위·입력·가정·오차·비교 기준; DPS를 승률로 바꾸지 않음 |
| TASK-030 | 로컬 UI | CLI 서비스 재사용, loopback·출력 escaping·경로 보호 |

각 작업의 시작 기록에는 수정할 파일, 범위 밖 항목, 관련 F/E-ID, 예상 검증 명령을 적습니다. 종료 시 구현 산출물·실제 실행 로그·미완료·다음 작업을 남깁니다. [작업 템플릿](../harness/templates/task.md)을 사용합니다.
