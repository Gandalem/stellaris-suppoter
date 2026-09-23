# 정적 파싱·현지화

목표는 엔진 복제가 아니라 원문을 보존하는 정적 탐색입니다. 현재 설치 파일을 제공받지 않았고 관련 Wiki 본문도 이번 조사에서 확보하지 못했습니다([출처](SOURCES.md)). 아래는 조사 후보와 구현할 지원 범위이며 최신 게임에서 모두 확인된 사실이 아닙니다.

## 데이터 경로 조사 후보

| 범주 | 경로 후보 | 최소 추출 |
|---|---|---|
| 기술 | common/technology/ | ID, 선행 참조, 비용·가중치 원문, 조건 |
| 함선 부품 | common/component_templates/ | ID/key, 수치 표현식, 제한 |
| 건물·지구·직업 | common/buildings/, common/districts/, common/pop_jobs/ | ID, 비용·생산·유지비 표현식 |
| 특성 | common/traits/ | ID, modifier·조건 |
| 정부·시빅·기원 | common/governments/ 및 실제 하위 경로 | ID, 타입·조건·DLC 표현식 |
| 전통·승천 | common/traditions/, common/ascension_perks/ | ID, 선행·효과 |
| 이벤트·보조 script | events/, common/scripted_triggers/, common/scripted_effects/ | namespace, ID, 참조, 조건·효과 원문 |
| 번역 | localisation/ 및 실제 언어별 구조 | key, 언어, 값, 위치 |

inventory에서 실재 경로를 먼저 확인합니다. 경로가 없으면 게임에 그 기능이 없다는 뜻이 아니라 해당 위치에서 못 찾았다는 뜻입니다. mapping과 지원 범위를 registry로 관리하며 기억에 의존해 폴더 이름을 고정하지 않습니다.

## lexer·AST

첫 지원은 공백/줄바꿈, # 주석, 중괄호, = 할당, > < >= <= 비교, quoted string과 escape, 숫자·identifier·변수 참조 원문입니다. 긴 연산자를 먼저 분리하고 문자열 안의 brace/#를 구조나 주석으로 처리하지 않습니다.

블록의 assignment와 bare scalar 혼합, 중복 키, namespace, 파일 변수는 순서 있는 노드로 보존합니다. typed block·매크로형 표현식·새 연산자 등 미지원 구조는 unknown 노드와 진단으로 남깁니다. 입력을 코드로 실행하지 않습니다.

UTF-8/BOM을 우선 지원합니다. decoding 실패를 replacement 문자나 임의 인코딩 추측으로 숨기지 않습니다. lexer byte span은 0-based half-open, line/column은 1-based이며 end는 exclusive입니다. CRLF는 한 번의 줄바꿈으로 계산합니다. 선두 UTF-8 BOM은 별도 token으로 보존하되 다음 실제 문자는 line 1/column 1에서 시작합니다. 위치는 문자별 map을 선할당하지 않고 token 순회 중 line/column cursor로 계산합니다. lexer 기본 자원 한도는 입력 16 MiB와 token 100,000개이며 byte 한도는 UTF-8 검증 전에, token 한도는 다음 Token/SourceSpan 생성 전에 적용합니다. 한도 초과는 LIMIT_EXCEEDED로 실패하며 입력을 잘라 성공 처리하지 않습니다. 문자열 미종결·brace 누락·예상 밖 EOF는 오류이며 조용한 성공이 아닙니다. AST 깊이 제한은 TASK-007에서 별도로 적용합니다.

## 도메인 adapter

TASK-008에서 기술 하나의 수직 슬라이스를 먼저 만듭니다. 이후 범주마다 합성 fixture, ID 식별법, 필드·조건·출처 보존, 중복 충돌, 참조 추출, unknown 동작을 테스트한 뒤 지원 목록에 추가합니다. AST를 수정하지 않고 EntityCandidate로 변환합니다.

potential, allow, prerequisites, weight, modifier 등의 이름만 보고 전체 게임 의미를 확정하지 않습니다. 읽은 숫자와 현재 제국에 적용되는 값은 다릅니다. 가중치는 후보군·조건·추첨 규칙 없이는 등장 확률이 아닙니다.

중복 ID는 모두 보존합니다. 파일 목록의 마지막 값이 실제 적용값이라고 가정하지 않습니다. 효과적인 정의 선택은 로드 규칙을 검증하는 F-017의 책임입니다.

## 현지화

일반 YAML reader로 무조건 처리하지 않습니다. 언어 header, key, 선택적 숫자 marker, quoted value, comment를 corpus로 검증하는 전용 reader를 만듭니다. marker는 metadata이며 게임 패치 버전이 아닙니다.

한국어 → 영어 → ID fallback과 각 출처를 기록합니다. 정적 치환은 깊이·방문 key 제한으로 순환을 차단합니다. 동적 scope, 아이콘·색상 태그, escape는 raw와 표시값을 분리하며 실행하지 않습니다. 번역 출처가 기술 정의 출처를 덮어쓰지 않습니다.

## 로컬 조사 보고

파일 수, encoding 분포, 성공/부분/실패 수, 미지원 구문 유형, 상대 경로 진단만 공개합니다. 원문·DLC 콘텐츠·세이브·개인 경로는 올리지 않습니다. 재현이 필요하면 직접 만든 최소 합성 사례를 사용합니다.
