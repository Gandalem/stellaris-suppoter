# 검색과 근거 기반 답변

## 검색 계약

같은 snapshot 안에서 ID exact → 정규화 이름 exact → 검증된 별칭 exact → 이름 prefix/substring → 설명 lexical 순으로 후보를 모읍니다. 검색용 문자열에만 Unicode NFC, 영문 casefold, 공백 정리를 적용합니다. 원문은 보존합니다. 자모 변환·음역·오탈자 교정은 평가 없이 추가하지 않습니다.

동점은 kind, game_id, 상대 경로, node occurrence로 안정적으로 정렬합니다. match_reason을 표시하며 범주·언어 필터를 질의 계약에 포함합니다. 별칭은 실제 표현과 테스트를 바탕으로 명시 관리합니다.

**TASK-011 구현 경계:** `SearchService.search(Query)`는 호출 시 active 또는 명시 snapshot을 한 번 고정하고, immutable SQLite v1 레코드로부터 세션 내 재생성 가능한 메모리 projection을 구성합니다. 최초 구축은 `fetchmany(128)`으로 제한된 배치 읽기이며 매 질의마다 `SnapshotRepository.entities()` 전체 조회를 하지 않습니다. Projection은 별도 영속 DB schema 또는 migration이 아니며, 한도가 초과되면 명시적으로 실패합니다. 정확한 별칭은 명시 등록과 source bytes 존재뿐 아니라 대상 entity_key의 정확한 정의 SourceRef 또는 중복 없는 같은 game ID의 localisation entry/value SourceRef 관계까지 확인한 경우에만 사용합니다. 동적/보호 문자열(색상 §, 아이콘 £, bracket, 미해결 $reference$, 미지원 escape)은 검증된 이름·설명으로 승격하지 않습니다. 정적 참조가 완전히 해석된 이름은 원본 번역 및 각 참조의 SourceRef와 선택 언어를 검색 결과에 함께 반환합니다. FTS5를 탐지하지만 기존 FTS+LIKE 중복 분기로 성능 향상을 주장하지 않으며 FTS5 지원 유무와 무관하게 parameterized LIKE 검색을 유지합니다. 검색 결과는 인용용 SourceRef만 제공하며 완성된 답변/CLI는 후속입니다.

## 한국어·SQLite

FTS5 가용성을 runtime에서 확인하고 없으면 ID·이름 fallback을 제공합니다. FTS tokenizer가 한국어 형태소 분석을 제공한다고 주장하지 않습니다. SQLite 문서에 따르면 trigram full-text 검색은 3 Unicode 문자 미만 substring을 반환하지 않습니다([S-02](SOURCES.md)). '합금' 같은 질의에는 별도 exact/prefix/parameterized substring 경로가 필요합니다.

사용자 입력은 SQL parameter로 전달하고 FTS query는 별도로 안전한 literal로 만듭니다. SQL parameterization만으로 FTS 문법 문제가 해결된다고 가정하지 않습니다. 따옴표·별표·괄호·AND/OR·한글 두 글자·공백을 테스트합니다. 무제한 전체 DB scan 대신 snapshot·길이·결과 제한을 적용합니다.

## v0.1의 답변

모델 없는 결정적 템플릿을 사용합니다. 내부 ID, 번역 이름과 fallback, 정적 필드, 조건, 파일·행·해시·snapshot, 경고를 표시합니다. 자연어 입력이 지원 범위를 넘으면 검색 가능한 범주와 제한을 설명하며 전략 상담을 지원하는 척하지 않습니다.

facts마다 실제 필드를 포함하는 SourceRef가 필요합니다. 관련 파일을 찾았다는 것만으로 인용이 되지 않습니다. 수치와 번역 설명의 출처를 구분합니다. 변경된 설치 파일 대신 과거 snapshot의 캐시를 인용하면 그 사실을 표시합니다.

예: '이 정의에는 비용 표현식 @demo_cost가 있습니다. 해당 변수의 적용값은 이 조회에서 확정하지 않았습니다.' 이는 실제 게임 비용이 아닙니다.

## 보류 기준

| 상황 | 동작 |
|---|---|
| 결과 없음 | not_found, 사실 생성 금지 |
| 같은 ID의 여러 정의 | ambiguous/partial, 각각 출처와 충돌 표시 |
| 버전 불명 | unknown, 최신 패치라고 부르지 않음 |
| 베타/정식 자료 충돌 | 채널 분리, 설치 문맥 우선 확인 |
| 미지원 조건·동적 효과 | 원문 보존, 실행 결과 보류 |
| 인용 원본 변경 | 보존된 snapshot 원문 또는 SOURCE_CHANGED |
| 연구 확률·전투 승률 | 필요한 입력과 미지원 계산 명시 |
| 모드 발견 | base_install 조회임을 표시, 적용 결과 단정 금지 |

## 후속 AI 계층

F-016은 snapshot, 검증된 필드/인용 ID, unknown 항목과 문맥 제한을 EvidencePacket으로 묶습니다. 모델 출력의 인용이 packet에 존재하는지, 수치가 근거와 일치하는지 검사합니다. 검증 실패 시 정적 출력으로 복귀하거나 답변을 보류합니다.

검색된 웹·모드 텍스트의 지시문은 데이터입니다. 모델에 포괄적인 파일·셸 권한을 주지 않습니다. 모델 미설정·타임아웃·예산 초과가 기본 검색을 막지 않습니다. 모델명·비용·외부 전송 동의 없이 cloud provider를 선택하지 않습니다.
