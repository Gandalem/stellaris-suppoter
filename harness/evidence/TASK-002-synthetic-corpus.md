# TASK-002 synthetic corpus evidence

날짜: 2026-09-22  
검증 commit: `f064032883e9ad4ed990a156cd86fae62d17937e`  
GitHub Actions: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35728494012

## 산출물

- `tests/fixtures/synthetic/corpus/`: 14개 project-authored synthetic input files.
- `tests/fixtures/synthetic/manifest.json`: 상대 경로, scenario, encoding, byte size, SHA-256.
- `tests/fixtures/synthetic/README.md`: provenance, scenario 목적, 이후 기대 동작.
- `scripts/generate_synthetic_corpus.py`: 외부 입력 없이 corpus와 manifest를 결정적으로 생성.
- `tests/test_synthetic_corpus.py`: provenance, scenario coverage, hash/size, byte reproduction, overwrite refusal, encoding edge, collision/localisation invariants.
- `.gitattributes`: fixture와 manifest의 line-ending normalization 차단.

## E-002 확인

### No copied game content

fixture의 ID, 영문/한글 명칭, 수치, 문자열은 이 프로젝트 테스트용으로 작성했고 `demo_*` 또는 synthetic marker를 사용했다. Stellaris 본편, DLC, 모드, localisation, save 원문을 입력으로 사용하거나 복사하지 않았다. generator는 정적 project-authored bytes만 포함하고 외부 파일/network/game installation을 읽지 않는다.

이 항목은 provenance와 self-review에 근거한 작성 이력 주장이다. 자동 테스트가 저작물 전체와 대조해 '세상 어디에도 같은 문장이 없다'는 것을 증명한다는 뜻은 아니다.

### Deterministic and labelled

- 모든 corpus file의 시작 부분을 byte-level synthetic marker로 검사.
- manifest가 14개 파일의 size/SHA-256을 검사.
- generator가 만든 `manifest.json`과 corpus를 committed bytes와 byte-for-byte 비교.
- normal/error/localisation/collision 필수 scenario가 manifest에 존재하는지 검사.
- BOM+CRLF와 invalid UTF-8 bytes를 별도 검사.
- generator가 비어 있지 않은 출력 디렉터리를 기본적으로 덮어쓰지 않는지 검사.

## 실제 실행

| 환경 | job | Python | pytest | Ruff | harness |
|---|---:|---:|---|---|---|
| ubuntu-latest | 106747919525 | 3.11.16 | 30 passed | success | success |
| windows-latest | 106747920808 | 3.13.15 | 30 passed | success | success |

두 job의 최종 conclusion은 `success`였다.

## 발견 및 수정

이전 run 35728394616에서 corpus 파일 자체는 byte 보존됐지만 Windows checkout이 `manifest.json`의 LF를 CRLF로 정규화하여 byte reproduction 테스트가 실패했다. `.gitattributes`에 manifest와 corpus를 `-text`로 지정한 후 final run 35728494012에서 양 플랫폼이 동일하게 통과했다.

## 한계

이 근거는 E-002 synthetic corpus provenance/determinism만 검증한다. 합성 script가 현재 Stellaris 엔진에서 실제로 유효하다는 의미가 아니며 lexer, AST parser, localisation resolver, 실제 설치 호환성은 아직 검증하지 않았다.
