# TASK-002 Synthetic corpus

## 식별·범위

작업 ID: TASK-002  
제목: Synthetic corpus  
관련 기능 / 평가 ID: F-004, F-006 / E-002  
기준 브랜치와 시작 commit: task/TASK-002-synthetic-corpus / 3d1233012fa37032b121921bbd28ee6d5d958b16  
선행 작업: TASK-001 done / E-001 pass  
사용자 요청: TASK-002 Synthetic corpus 구현.

구현한 것:
- 프로젝트가 직접 작성한 synthetic script/localisation corpus 14개 입력 파일.
- normal, lexical edge, malformed/error, localisation fallback/cycle/duplicate, duplicate ID/collision, snapshot isolation, depth limit 시나리오.
- UTF-8 BOM+CRLF와 invalid UTF-8 byte fixture.
- 상대 경로, scenario, encoding, size, SHA-256을 가진 manifest.
- provenance/기대 동작 README.
- 결정적 corpus generator와 byte-for-byte 재생성 테스트.
- Git line-ending normalization으로부터 fixture/manifest를 보호하는 .gitattributes.

구현하지 않은 것:
- lexer/parser/localisation resolver 자체.
- 실제 Stellaris 원문, 번역, DLC/모드 데이터.
- 실제 엔진 의미나 최신 게임 구문 호환성 주장.
- 게임 설치 폴더 접근.

## 수용 조건 결과

- 모든 fixture가 byte 수준에서 `# origin: synthetic` 표식 보유: 통과.
- normal/error/localisation/collision 시나리오 문서화 및 manifest 등록: 통과.
- generator 출력과 committed corpus/manifest byte-for-byte 비교: Linux/Windows 통과.
- manifest SHA-256/size 검증: 통과.
- BOM+CRLF/invalid UTF-8 byte 특성 검증: 통과.
- provenance에 실제 게임/DLC/mod/localisation/save 원문을 복사하지 않았음을 명시: 완료.
- Windows checkout 줄바꿈 변환 방지: .gitattributes로 고정 후 통과.

## 검증

최종 검증 대상 commit: `f064032883e9ad4ed990a156cd86fae62d17937e`  
GitHub Actions run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35728494012

- Ubuntu / Python 3.11.16 / job 106747919525: 30 tests passed, Ruff success, harness success.
- Windows / Python 3.13.15 / job 106747920808: 30 tests passed, Ruff success, harness success.
- generator는 network/game data를 읽지 않고 정적 project-authored bytes만 생성.
- run 35728394616에서 Windows가 manifest CRLF normalization 때문에 한 번 실패했고, manifest를 `-text`로 고정한 뒤 최종 run에서 통과했다.

## 종료

상태: done  
평가 E-002: pass  
F-004/F-006: in_progress (실제 parser/localisation 구현은 남음)  
근거: [synthetic corpus evidence](../evidence/TASK-002-synthetic-corpus.md)  
검토: self_review  
다음 번호 작업: TASK-003 Configuration and doctor.
