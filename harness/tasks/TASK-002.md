# TASK-002 Synthetic corpus

## 식별·범위

작업 ID: TASK-002  
제목: Synthetic corpus  
관련 기능 / 평가 ID: F-004, F-006 / E-002  
기준 브랜치와 commit: task/TASK-002-synthetic-corpus / 3d1233012fa37032b121921bbd28ee6d5d958b16  
선행 작업: TASK-001 done / E-001 pass  
사용자 요청: TASK-002 Synthetic corpus 구현.

이번에 구현할 것:
- 프로젝트가 직접 작성한 합성 script/localisation corpus.
- 정상, lexical edge, malformed/error, localisation fallback/cycle/duplicate, duplicate ID/collision 시나리오.
- UTF-8 BOM + CRLF 및 invalid UTF-8 byte fixture.
- corpus manifest와 provenance 문서.
- corpus를 결정적으로 재생성하는 표준 라이브러리 generator.
- committed corpus가 generator 출력과 byte-for-byte 일치하는 테스트.

이번에 구현하지 않을 것:
- lexer/parser/localisation resolver 자체.
- 실제 Stellaris 원문, 번역, DLC/모드 데이터.
- 실제 엔진 의미나 최신 게임 구문 호환성 주장.
- 게임 설치 폴더 접근.

## 수용 조건

- 모든 커밋 가능한 fixture는 origin=synthetic으로 명시.
- 정상·오류·현지화·충돌 시나리오가 README/manifest에 문서화.
- generator를 두 번 실행해도 동일한 byte corpus/manifest가 생성.
- manifest의 SHA-256과 size가 실제 파일과 일치.
- UTF-8/BOM/CRLF/invalid UTF-8 fixture의 byte 특성이 테스트로 확인.
- 실제 게임 콘텐츠를 복사하지 않았다는 provenance와 작성 원칙을 기록.
- E-002 관련 테스트가 Linux/Windows에서 통과.

## 검증 계획

```sh
python scripts/generate_synthetic_corpus.py --output <temp-dir>
python -m pytest
python -m ruff check .
python scripts/check_harness.py
```

GitHub Actions의 Ubuntu/Python 3.11 및 Windows/Python 3.13에서 실행 결과를 확인한 뒤 E-002를 pass로 변경한다.

## 종료

완료 시 TASK-002=done, E-002=pass. F-004/F-006은 후속 parser/localisation 구현이 남으므로 in_progress로 전환한다. 다음 번호 작업은 TASK-003 Configuration and doctor.
