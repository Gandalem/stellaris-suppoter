# 업데이트·버전·최신성

## 서로 다른 세 가지 상태

설치 데이터의 버전, 외부 공식 정식 버전, 외부 자료를 마지막 확인한 시점은 다릅니다. 모든 답변은 어느 snapshot에 근거하는지 표시합니다. '오늘 색인했다'고 '최신 게임 규칙'이라고 부르지 않습니다. 과거 대화의 패치 번호·코드명·출시 일정은 검증된 데이터가 아닙니다.

v0.1은 사용자가 지정한 설치 파일과 unknown을 처리합니다. 인터넷 최신 패치 확인은 F-015에서 추가합니다. beta/dev diary/planned/console/PC를 같은 채널로 합치지 않습니다.

## 설치 데이터 갱신

전체 상대 경로와 원문 해시로 추가·수정·삭제를 탐지합니다. mtime/크기는 성능 힌트일 뿐 동일 내용의 증명이 아닙니다. 첫 inventory와 활성화 직전 재검사 사이에 파일이 달라졌으면 새 snapshot의 활성화를 중단합니다. 게임 업데이트가 끝난 후 재시도하도록 안내합니다.

기존 원문과 active snapshot은 유지합니다. 바뀐 파일의 엔티티·번역·관계를 재생성하고 제거된 항목도 처리합니다. 새 snapshot과 DB 보조 색인 정합성을 확인한 후 원자적으로 활성화합니다. 파서/adapter/정책 변경도 재색인 조건입니다.

cache freshness는 fresh|changed|unchecked|unavailable로 표시합니다. fresh는 지정한 시점에 설치 원문을 확인했다는 뜻이며 공식 최신 버전이라는 뜻이 아닙니다. 확인 실패 시 기존 checked_at을 현재 시각으로 바꾸지 않습니다.

## F-015의 외부 수집 계약

공식 패치 공지·개발자 일지·Steam 공식 공지를 우선하되 출처의 주장 목적을 구분합니다. Steam의 GetNewsForApp v2와 Stellaris app ID는 [S-03/S-04](SOURCES.md)를 참고합니다. 뉴스 feed에 들어왔다는 사실만으로 공식 패치나 적용 완료라고 분류하지 않습니다.

저장 필드: canonical_url, source_name, author/publisher, article_id, published_at, retrieved_at, channel, platform, version_label, content_hash, excerpt, classification_evidence, fetch_status. 날짜가 없으면 unknown이며 제목의 추정 날짜를 실제 출시일로 만들지 않습니다.

기본 네트워크는 off입니다. 명시적인 sync 작업에서만 허용 도메인, 요청 수·응답 크기·timeout·redirect·재시도 한도를 적용합니다. robots·이용 조건·인용 범위를 검토하고 차단된 페이지를 우회 수집하지 않습니다. 무제한 크롤링 대신 필요한 변경 정보와 출처를 보관합니다.

오프라인·429·timeout·페이지 구조 변경이면 캐시 시점과 실패 이유를 알리고 기본 로컬 검색은 유지합니다. 최신 확인 불가능을 '변경 없음'으로 기록하지 않습니다. 자동 스케줄러는 후속 승인 항목이며 앱을 만들었다는 이유만으로 백그라운드 갱신을 약속하지 않습니다.

## 충돌 우선순위

'내 설치에서 이 필드가 무엇인가'는 해당 snapshot 원문이 근거입니다. '현재 정식 패치에서 무엇이 바뀌었나'는 검증된 공식 공지와 대상 버전이 근거입니다. Wiki·커뮤니티는 설명·가설 자료이며 실제 설치의 수치와 충돌하면 각 문맥을 표시합니다. 서로 다른 버전의 출처를 하나의 수치로 합치지 않습니다.


## 설치 버전·분기 증거 정책

TASK-005의 로컬 증거 모델은 `game_version`, `build_id`, `branch`를 서로 독립 필드로 유지합니다. `game_version_source`와 `branch_source`는 `metadata|user_reported|unknown`이며, metadata가 없을 때만 user-reported 값을 해당 출처 그대로 사용할 수 있습니다. 서로 충돌하면 metadata를 유지하고 conflict diagnostic을 남깁니다.

`build_id`는 버전 라벨로 변환하지 않습니다. build ID만 있으면 `game_version=null`, `game_version_source=unknown`이며 VERSION_UNKNOWN 상태를 유지합니다. 이 정책은 실제 최신 버전을 알아낸다는 의미가 아닙니다.

DLC는 `installed`, `owned`, `enabled`를 각각 `true|false|null`로 유지하고 각 필드에 독립 source/evidence를 둡니다. 파일 존재는 installed 근거가 될 수 있지만 owned나 enabled를 자동으로 true로 만들지 않습니다. launcher/platform/user report도 다른 필드를 암묵적으로 덮어쓰지 않습니다.


### 원본 version evidence 보존

선택된 `game_version`, `build_id`, `branch`와 수집된 원본 observation은 분리합니다. 각 non-empty observation은 field, source(metadata|user_reported), raw_value, normalized_value, disposition을 보존합니다. disposition은 selected|corroborating|conflict|suppressed_by_metadata|unrecognized입니다.

metadata branch가 존재하지만 stable/beta로 해석되지 않으면 이는 "metadata 없음"이 아닙니다. 이 경우 branch는 unknown으로 유지하고 user-reported branch를 선택하지 않습니다. metadata 원문은 unrecognized, 유효한 user report는 suppressed_by_metadata observation으로 남깁니다.

원본 observation은 persistence/private evidence용 `to_dict()`에 포함하고, 공개 보고용 `to_public_dict()`에서는 제외합니다. Diagnostic 메시지는 원본 version/build/branch 문자열을 삽입하지 않는 정적 문구를 유지합니다.
