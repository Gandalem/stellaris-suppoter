# 설계 결정 기록

상태: 초기 설계 선택. 사용자 요구나 실제 데이터 검증으로 바뀔 수 있으며 변경 시 사유·영향·평가를 기록합니다. 작성일 2026-09-22.

| ID | 결정 | 이유·대안 | 재검토 조건 |
|---|---|---|---|
| ADR-001 | 재학습보다 설치 데이터·검색·근거 도구를 먼저 만든다 | 수치와 규칙을 외부 데이터로 교체 가능하게 함; 모델 기억을 원본으로 사용하지 않음 | 평가에서 검색 기반으로 해결되지 않는 구체적 요구가 확인될 때 |
| ADR-002 | Python 3.11+ 단일 패키지, stdlib 중심 | TOML/SQLite/CLI를 단순한 배포로 시작; 별도 서버·Node·컨테이너 불필요 | 성능·UI 요구가 실제 병목을 보일 때 |
| ADR-003 | CLI와 결정적 정적 답변을 먼저 만든다 | API·모델 비용 없이 인용·검색을 검증 | v0.1 합성·로컬 게이트 통과 후 모델/UI 추가 |
| ADR-004 | 순서·중복·원문 위치를 보존하는 AST | 일반 dict 변환은 반복/조건/근거 손실 위험 | 실제 구문 조사에 따른 지원 집합 확장 |
| ADR-005 | SQLite와 lexical/exact 검색으로 시작 | 운영 구성 단순화; 한국어 짧은 질의 fallback 직접 평가 | 정답 corpus에서 벡터 검색의 추가 가치가 측정될 때 |
| ADR-006 | immutable snapshot과 출처를 핵심 계약으로 둔다 | 버전 혼합·stale 인용 방지, 재현 가능성 | 저장 비용 최적화가 필요해도 출처 재현 조건은 유지 |
| ADR-007 | 모드·세이브·전투 계산은 별도 단계 | 로드 규칙·동적 상태·엔진 의미를 추측하지 않음 | 범주별 실증과 필요 입력·한계가 확보될 때 |
| ADR-008 | 실제 원문은 개인 로컬, 합성 fixture만 공개 | 공개 저장소의 데이터·개인정보 경계 유지 | 외부 데이터는 별도 이용 조건과 승인 검토 후 |
| ADR-009 | 원장과 실행 증거로 완료를 관리한다 | 다른 에이전트/세션도 상태를 이어받음 | 원장 규모가 커지면 형식 확장하되 기존 ID 보존 |
| ADR-010 | Windows를 첫 사용자 검증 목표로 가정 | 사용자 OS가 아직 없으므로 가정으로만 둠; Linux 자동 테스트 | 사용자 OS 확인 시 호환성 목표 갱신 |
| ADR-011 | game_root는 자동 탐색하지 않고 data/config만 OS별 안전 기본 위치를 사용 | Steam 경로 추측·환경변수 오염을 피하고 개인 데이터는 게임 트리와 분리; TOML 상대 경로는 설정 파일 기준 | 실제 사용자 설치 흐름에서 자동 탐색이 명시적으로 필요해지고 안전한 증거 기반 방법이 검증될 때 |
| ADR-012 | localisation은 제한된 문법 reader와 deterministic bounded resolver를 분리하고 원본 source bytes/span을 공유 | 범용 YAML은 순서·중복·byte span 손실이 있고 즉시 문자열 확장은 반복 참조 시 메모리/CPU 증폭을 초래한다. SOURCE hash 검증 후 raw reference와 출력/방문/스캔 예산을 적용하고 검증되지 않은 정의 우선순위를 ambiguous로 처리한다. F-006/TASK-009/E-015~017 관련 | 실제 게임 현지화 구문 조사에서 지원 범위를 변경할 근거가 확보되거나 TASK-010 snapshot 계약과 충돌할 때 |
| ADR-013 | TASK-010 SQLite v1은 snapshot ID와 active pointer를 분리하고 cache 검증→staging→BEGIN IMMEDIATE atomic pointer 전환을 사용한다 | 2026-10-11; F-007/TASK-010/E-018/E-019. 후보 ID는 NFC 필수·구분자 slash·원형 대소문자 보존·충돌 거부, 정렬된 상대 경로/출처/hash + canonical UTF-8 JSON 정책으로 생성한다. SQLite WAL/FULL/foreign_keys/250ms busy timeout 사용; 원본은 개인 SHA cache에서 atomic replace + 검증 후 DB에 연결한다. DB와 filesystem은 별도 원자성 영역이므로 cache가 누락/손상됐으면 ready 전환 및 활성화를 거부한다. duplicate game_id는 별도 occurrence, raw는 shared cache. 자동 migration·실제 게임 규칙/FTS는 미지원. | 실제 OS DB lock/cache 실패 회귀나 상위 schema migration 수요가 확인되면 검증과 승인 후 개정 |

| ADR-014 | TASK-011 검색은 SQLite v1 스키마를 변경하지 않고 재생성 가능한 per-snapshot 메모리 SQLite projection과 제한된 배치 읽기를 사용한다 | 2026-10-11; F-008/TASK-011/E-020~022. 영속 FTS/검색 테이블 확장은 schema migration/rollback 정책 없이 기존 snapshot을 손상시킬 수 있어 제외한다. 최초 구축은 bounded iterator와 64MiB 합성 projection 입력 한도로 제어하고, warm query는 SQL limit/rank로 작동한다. FTS5는 runtime 선택이며 일반 LIKE 경로를 보존한다. 트레이드오프: cold-build 비용·메모리 제한·서비스 재시작 시 재구축. | 실제 10k synthetic 성능/메모리 측정이나 FTS 운영 요구에서 병목이 확인되면 ADR 개정 후 migration 별도 검토 |

새 결정은 문제, 선택, 대안, trade-off, 영향 F/TASK/E-ID, migration, 승인/검토, 날짜를 기록합니다. 폐기된 결정을 삭제하지 말고 superseded와 새 ID를 연결합니다. 패치·모델·라이브러리의 최신 여부는 설계 결정이 아니라 확인해야 할 외부 사실입니다.


## ADR-015 — Windows 게임 오버레이 방향 (2026-10-12)

F-020의 최종 사용자 경험은 게임 위에 뜨는 별도 Windows 오버레이로 계획합니다. PySide6/Qt는 후보이고 확정이 아닙니다. TASK-022 이후 선택적 TASK-032/E-048에서 전역 핫키 충돌, 접힘 입력 통과, 게임 종료·최소화와 창/DPI 위험을 검증합니다. TASK-029와 TASK-032 후 TASK-030/E-046이 최종 구현을 담당합니다. 게임 주입·그래픽 후킹·메모리 읽기를 배제하며, 실제 Windows 실험에서 실패하면 프레임워크/호환 범위를 다시 결정합니다. SQLite migration 없음. 계획 승인·기능 완료·실게임 호환성은 별개입니다.
