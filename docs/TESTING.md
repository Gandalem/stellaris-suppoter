# 테스트 전략

문서 검사, 검사기 자체 테스트, 제품 테스트, 실제 게임 검증을 구별합니다. 현재 제품 테스트와 게임 fixture는 아직 없습니다. [평가 사례](../harness/evals.jsonl)는 설계된 사례이며 모두 not_run으로 시작합니다.

## 테스트 계층

| 계층 | 검증 대상 | 데이터 |
|---|---|---|
| harness | JSON 원장, ID·의존성·근거·문서 링크 | 작은 임시 문서 저장소 |
| unit | lexer, AST, localisation, 정규화, hashing | 직접 만든 문자열·bytes |
| integration | inventory → parser → DB → search → citation | 합성 디렉터리 corpus |
| CLI | 종료 코드, stdout JSON, stderr 로그, 설치 후 명령 | 임시 가상환경·합성 corpus |
| security | 경로·권한·한도·통신·정보 노출·중단 | 악조건 합성 입력 |
| evaluation | 검색 정답·근거 위치·보류·버전 격리 | 버전이 고정된 합성 정답 세트 |
| local acceptance | 실제 설치 데이터의 경로·구문·도메인 차이 | 사용자 PC, 비공개 원문 |

## fixture 정책

모든 커밋 가능한 fixture는 직접 만든 합성 데이터입니다. 실제 게임·모드·번역·세이브를 복사하지 않습니다. 이름은 demo_/synthetic_ 계열이고 origin: synthetic을 명시합니다. scenario별 README에 목적·입력·정답·지원 범위를 기록합니다. TASK-002가 corpus를 만들고 TASK-018이 평가 runner를 연결합니다.

필수 시나리오: 정상·중복·혼합 블록, 문자열 속 brace/#, escaped quote, BOM/CRLF, 미종결 문자열/brace, 비UTF-8, 깊이·파일 한도, 미지원 표현식, 한국어/영어/ID fallback, 번역 순환·중복, 같은 ID의 다른 snapshot, 빈/짧은/특수 질의, 누락 참조·그래프 순환, 파일 추가/삭제/변경, 색인 중 파일 변경, 취소·DB 실패, 입력 지시문·개인 경로 노출.

## 실행 규칙

unit/integration/evaluation은 네트워크를 막고 실제 사용자 홈·게임 폴더에 접근하지 않습니다. 임시 디렉터리와 명시적 경로를 사용합니다. seed·locale·timezone·정렬·시간 주입을 고정합니다. filesystem·환경·network 대체는 pytest의 monkeypatch 등 공식 API를 참고합니다([S-06](SOURCES.md)).

한 테스트가 다른 테스트의 DB·상태를 재사용하지 않습니다. 실제 시간·외부 모델 출력·최신 공지에 단위 테스트 정답을 의존시키지 않습니다. Windows 경로·잠금, Linux 경로·permission을 각각 확인합니다. OS가 다른데 실행했다고 주장하지 않습니다.

## 현재 명령

```sh
python scripts/check_harness.py
python -m unittest discover -s tests_harness -v
```

TASK-001 이후 제품용 pytest와 Ruff 검사를 추가합니다. TASK-018 이후 평가 runner의 정확한 명령을 문서에 적습니다. 아직 없는 명령은 성공 로그에 넣지 않습니다.

## 품질 게이트

수정한 기능의 실패 재현 → 관련 unit/integration → 전체 회귀 → 인용/안전/버전 평가 → 패키지 스모크 순서입니다. 한도·보안·unknown 처리의 회귀는 필수입니다. coverage는 참고 지표이며 100% 숫자만으로 정확성을 보장하지 않습니다. v0.1 전체 합성 필수 평가가 통과하기 전 verified로 바꾸지 않습니다.

실패한 테스트를 삭제·skip하거나 broad exception으로 숨겨 통과시키지 않습니다. flaky test는 seed와 원인을 기록하고 수정합니다. 미실행·환경상 불가·실제 실패를 각각 not_run/blocked/fail로 구분합니다.
