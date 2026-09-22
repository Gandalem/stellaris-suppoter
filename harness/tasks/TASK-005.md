# TASK-005 Version and DLC evidence

## 식별·범위

작업 ID: TASK-005  
제목: Version and DLC evidence  
관련 기능 / 평가 ID: F-003 / E-007, E-008  
기준 branch: task/TASK-005-version-dlc-evidence  
시작 main commit: 472aad700e24e03b20081f13b653502b673c7d00  
선행 작업: TASK-004 done; 실제 main push CI 확인 완료.

## 구현할 것

- version evidence에서 metadata/user_reported/unknown 구별.
- build_id를 별도 evidence로 보존하고 patch/version으로 추정하지 않음.
- branch stable/beta/unknown과 source 분리.
- metadata와 user report 충돌 시 deterministic precedence + diagnostic.
- DLC installed/owned/enabled를 독립 tri-state evidence로 모델링.
- filesystem/platform/launcher/user_reported/unknown source와 evidence detail 보존.
- 상충하는 DLC signal을 임의 수정하지 않고 diagnostic과 함께 원값 보존.
- deterministic dict serialization과 합성 pytest.

## 구현하지 않을 것

- 실제 Stellaris 설치 metadata 파일 위치 추정.
- 현재 최신 정식 패치 웹 확인.
- Steam/launcher ownership API 호출.
- 실제 사용자 DLC 소유·활성 상태 판단.
- build ID → patch version 매핑.
- mod/save semantics.

## 수용 조건

E-007:
- metadata와 user_reported version을 구별한다.
- 아무 version evidence가 없으면 null/unknown + VERSION_UNKNOWN.
- build ID만 있어도 game_version은 unknown.
- branch evidence의 source와 충돌을 보존한다.

E-008:
- installed=true만으로 owned/enabled를 추론하지 않는다.
- installed/owned/enabled 각각 true|false|null과 독립 source/evidence를 가진다.
- 상충하는 signal은 덮어쓰지 않고 explicit diagnostic으로 남는다.

## 검증 계획

```sh
python -m pytest tests/test_versioning.py -v
python -m pytest
python -m ruff check .
python scripts/check_harness.py
```

실제 게임 설치 acceptance는 TASK-021에 남는다.


## Candidate 검증

기능 candidate `44ff8d3e7aa0b9de03888a38cb19e65a483a916e`에서 다음을 검증했다.

- E-007: version 없음 → null/unknown + VERSION_UNKNOWN.
- build_id만 존재 → build_id는 보존하지만 game_version으로 변환하지 않음.
- user-reported version/branch는 user_reported provenance 유지.
- metadata와 user report 충돌 시 metadata를 유지하고 conflict diagnostic.
- unsupported branch label은 unknown + diagnostic.
- E-008: installed=true만으로 owned/enabled를 추론하지 않음.
- installed/owned/enabled 각각 독립 source/evidence 유지.
- enabled=true / installed=false 같은 상충 signal도 덮어쓰지 않고 diagnostic.
- 알려진 true/false 상태에 source=unknown 사용을 거부.

CI run 35750105437:
- Ubuntu/Python 3.11: 전체 94 passed; versioning 13 passed; Ruff/harness success.
- Windows/Python 3.13: 94 collected, 93 passed + 기존 POSIX-only inventory 1 skipped; versioning 13 passed; Ruff/harness success.

E-007/E-008은 pass지만 TASK-005는 reviewer 재검토와 main 병합 전까지 `doing`으로 유지한다. 실제 게임 설치 버전은 여전히 검증하지 않았고 `latest_game_version=null`을 유지한다.

근거: [TASK-005 evidence](../evidence/TASK-005-version-dlc-evidence.md)


## PR #11 review follow-up

최초 candidate 검토에서 두 가지 계약 누락이 재현되어 E-007을 재검증한다.

1. metadata branch가 존재하지만 stable/beta로 해석되지 않을 때 user-reported branch로 fallback하지 않는다.
2. metadata/user conflict와 unrecognized branch의 원본 observation을 선택 결과와 별도로 직렬화해 보존한다.

보완 모델은 `VersionObservation`을 추가하고 field/source/raw_value/normalized_value/disposition을 persistence representation에 포함한다. 공개 `to_public_dict()`는 raw observations를 제외하며 diagnostics도 정적 메시지를 유지한다.

기존 E-007/E-008 성공 evidence는 삭제하지 않는다. E-007만 follow-up CI 전까지 재검증 상태로 두고 E-008은 기존 pass를 유지한다.
