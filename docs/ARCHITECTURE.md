# 아키텍처

## 설계 선택

v0.1은 단일 Python 패키지와 개인 로컬 SQLite DB를 사용하는 모듈형 프로그램입니다. CLI를 먼저 만들고 모든 기능은 UI와 무관한 서비스 계층을 호출합니다. 정적 검색에 LLM·서버·외부 DB를 요구하지 않습니다. 아래 트리는 예정 구조이며 현재 구현 상태가 아닙니다.

```text
src/stellaris_supporter/
  cli.py                  # argparse, 출력/종료 코드
  config.py               # TOML, 경로/한도 검증
  diagnostics.py          # 코드가 있는 진단 객체
  discovery/              # 안전한 파일 목록, 버전 증거
  parsing/                # tokens, AST, localisation
  domain/                 # 범주별 adapter, reference extractor
  storage/                # SQLite schema, transactions, snapshots
  search/                 # normalization, lookup, ranking
  answers/                # deterministic formatter, citations
  services/               # index, query, diff orchestration
  providers/              # 후속: network/LLM 격리
```

## 데이터 흐름

명시적 설정 → 루트·출력 경계 확인 → 허용 파일 목록과 해시 → 개인 원문 캐시 → lexer/AST → 도메인 adapter·번역 → 출처 포함 엔티티 → staging snapshot → 무결성 확인 → 원자적 활성화 → 검색 → 정적 답변.

각 단계는 이전 단계의 진단을 보존합니다. 수집 원문을 바로 모델에 보내거나 게임 스크립트를 실행하지 않습니다. v0.1의 context_kind는 synthetic 또는 base_install입니다. 모드 적용이 검증되기 전 effective를 사용하지 않습니다.

## 인터페이스 경계

| 경계 | 입력 → 출력 | 부작용 |
|---|---|---|
| InventoryScanner | RootPolicy → Inventory + Diagnostics | 허용 루트 읽기만 |
| ScriptParser | SourceBytes → OrderedAST + Diagnostics | 없음 |
| LocalisationParser | SourceBytes → LocalisationEntries | 없음 |
| DomainAdapter | ParseResult + SourceRef → EntityCandidates + Relations | 없음 |
| SnapshotRepository | 검증된 records → staging/ready snapshot | 개인 data_dir 안 쓰기 |
| SearchService | Query + SnapshotID → SearchResult | 활성 스냅샷 읽기만 |
| AnswerFormatter | SearchResult → AnswerEnvelope | 없음 |
| Provider (후속) | 최소 근거 패킷 + Consent + Budget → ProviderResult | 별도 허용된 통신만 |

파서가 DB를 호출하거나 검색기가 네트워크를 호출하지 않습니다. 로그와 사용자 출력은 별도 채널입니다. SQLite 구현은 Repository 뒤에 두고 CLI와 parser에 SQL을 섞지 않습니다.

## 스냅샷과 정합성

파일 해시는 원본 bytes 기준입니다. 같은 내용의 캐시 재사용은 가능하지만 서로 다른 상대 경로의 출처를 합치지 않습니다. 동일 corpus·분석 정책·문맥의 snapshot_id는 안정적이어야 합니다. 수집 시각·개인 절대 경로는 콘텐츠 지문에서 제외합니다.

개인 캐시에 원본 bytes를 보존하여 업데이트 후에도 기존 인용을 재현할 수 있게 합니다. 캐시 파일명은 해시이며 게임 파일 이름을 임의 경로로 쓰지 않습니다. 원문 캐시·DB는 공개 산출물이 아닙니다.

한 번에 writer 하나만 허용합니다. building snapshot은 조회 대상이 아닙니다. 파일 수집 후와 활성화 전의 inventory가 달라지면 전환을 중단합니다. 데이터 오류가 있는 partial snapshot은 --allow-partial을 명시했을 때만 활성화하며 답변에 상태를 전파합니다. 경로 탈출·보안 한도 위반은 partial로 우회할 수 없습니다.

## 오류와 자원

외부 입력의 오류는 Diagnostic(code, severity, message, source_ref, remediation)으로 모읍니다. 오류 원문에 비밀 값이나 절대 경로를 넣지 않습니다. 파일·바이트·깊이·개수·검색 길이에 한도를 적용하고 결과가 잘렸으면 truncated=true와 원인을 출력합니다. 무한 재귀 대신 깊이 제한과 방문 집합을 사용합니다.

저장소 손상·중단·스키마 불일치는 [운영·복구](OPERATIONS.md)를 따릅니다. 성능 개선은 기준선 측정 뒤 추가하며 재현성과 출처 보존을 희생하지 않습니다.
