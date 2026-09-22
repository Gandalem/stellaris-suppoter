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
