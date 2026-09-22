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

## 원격 전체 검사: 확인 완료

검증한 제품 문서 commit: b919888c54472a7a5bc37222468f75ea160240b7.
[GitHub Actions 실행 35726240940](https://github.com/Gandalem/stellaris-suppoter/actions/runs/35726240940)의 job·step 결론을 실제 조회했다.

| 환경 | 원장·상대 Markdown 파일 링크 | 검사기 자체 회귀 | job 결론 |
|---|---|---|---|
| ubuntu-latest / Python 3.11 | success | success | success |
| windows-latest / Python 3.13 | success | success | success |

실행 명령:

```sh
python scripts/check_harness.py
python -m unittest discover -s tests_harness -v
```

Linux job 106740458010은 2026-09-22 12:17:01 UTC에, Windows job 106740457849는 12:17:14 UTC에 success로 완료되었다. 두 job 모두 실제 검증 step과 자체 테스트 step이 success였다. 이는 전체 원격 문서 묶음을 checkout한 환경의 결과이다.

이 기록 추가 commit 자체는 위 검증 commit 뒤에 만들어진다. 결과는 명시된 commit에 대한 근거이며 이후 변경의 검사 결과는 PR 체크에서 별도로 확인한다. 외부 웹 URL·Markdown heading anchor·evidence 내용의 진실성·게임 의미까지 자동 검사한 것은 아니다.

## 제품 상태

20개 기능 planned, 30개 작업 todo, 46개 평가 not_run. 이 파일을 제품 기능의 완료 evidence로 사용하지 않는다. 실제 게임 데이터와 Windows 제품 실행, 성능, 모델 답변, 세이브 해석은 검증하지 않았다.
