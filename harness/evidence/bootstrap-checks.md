# 부트스트랩 검증 기록

대상: 문서 하네스와 검사기. 제품 구현·게임 분석 평가가 아니다. 날짜: 2026-09-22. 검토: self_review.

## 실제 로컬 실행

환경: Linux, Python 3.13.5. 전체 원격 저장소 clone이 아니라 직접 작성한 검사기·테스트를 가진 작업 공간에서 실행했다.

```sh
python -m unittest discover -s tests_harness -v
```

실제 결과:

```text
Ran 18 tests in 1.476s
OK
exit code: 0
```

검사기 SHA-256: c6df69dad1211c3317f693422d67a8a9fd445dfa1a0403491628b73ec384021e
테스트 SHA-256: dcc074c970d0fa7ed234ba596670c7434b3d2c3ac593c4151e8e81bb2b508183

회귀 범위: 정상 planned 원장, 중복 ID, 의존성 순환, 잘못된 참조, 근거 없는 완료/검증/pass, 깨진 문서 링크, 외부 링크 미접속, Unicode 상대 경로, unsafe evidence 경로, blocked 이유, active 상태 불일치, 잘못된 상태/JSON, 완료 후 next_task=null, CLI의 product_tests_executed=false, malformed 입력의 통제된 실패.

## 원격 전체 검사

이 기록을 처음 작성한 시점에는 GitHub 전체 문서 링크 검사와 CI matrix 실행 결과가 아직 확인되지 않았다. 워크플로 등록만으로 통과로 기록하지 않는다. 실제 run 결과가 확인되면 commit·run URL·job별 결론을 아래에 추가한다.

## 제품 상태

20개 기능 planned, 30개 작업 todo, 46개 평가 not_run. 이 파일을 제품 기능의 완료 evidence로 사용하지 않는다. 실제 게임 데이터와 Windows 제품 실행, 성능, 모델 답변, 세이브 해석은 검증하지 않았다.
