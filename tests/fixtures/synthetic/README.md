# Synthetic corpus

이 디렉터리는 Stellaris Supporter의 parser/localisation 테스트를 위해 **프로젝트에서 직접 작성한 가상 데이터**입니다.

## Provenance

- origin: `synthetic`
- Stellaris 본편, DLC, 모드, 번역, 세이브의 문장·수치·ID를 복사하지 않았습니다.
- `demo_*` ID, 영문/한글 명칭, 수치와 문자열은 이 테스트를 위해 새로 작성했습니다.
- 구조는 정적 parser를 시험하기 위한 게임 스크립트 계열의 가상 문법입니다. 현재 Stellaris가 이 모든 예시를 실제로 허용한다는 의미가 아닙니다.
- 실제 게임 호환성은 별도의 비공개 local acceptance에서만 확인합니다.

## 시나리오

| 종류 | 핵심 파일 | 이후 기대 동작 |
|---|---|---|
| normal | `common/technology/00_demo_normal.txt` | ID, 변수, prerequisites, nested condition/weight를 원문 위치와 함께 보존 |
| lexical edge | `02_demo_lexical_edges.txt` | 문자열 안 `#`, `{}`, escaped quote를 구조/주석으로 오인하지 않음 |
| collision | `01_demo_collision.txt`, localisation collision, snapshots | 중복 ID/키/정의를 덮어쓰지 않고 모두 보존 |
| localisation | English/Korean files | ko → en → ID fallback 후보, 참조 cycle, duplicate, dynamic text를 구별 |
| malformed | `malformed/` | 미종결 string/block과 미지원 operator를 조용한 성공으로 처리하지 않음 |
| encoding | `encoding/` | UTF-8 BOM+CRLF span과 invalid UTF-8 오류를 명시적으로 다룸 |
| limits | `limits/depth_130.txt` | 기본 깊이 128보다 깊은 입력의 bounded failure를 시험 |
| snapshots | `snapshots/alpha`, `beta` | 같은 ID의 서로 다른 synthetic snapshot을 섞지 않음 |

## 결정성

`manifest.json`은 각 corpus 파일의 상대 경로, 시나리오, encoding label, byte 크기와 SHA-256을 기록합니다. 시간, 절대 경로, OS 정보를 넣지 않습니다.

재생성은 반드시 임시 디렉터리에서 먼저 확인합니다.

```sh
python scripts/generate_synthetic_corpus.py --output ./tmp-synthetic
```

`--force`도 출력 디렉터리 전체를 삭제하지 않습니다. 기존 `manifest.json`의 `origin`/`generator`와 관리 파일 목록이 소유권을 증명할 때만 그 관리 파일을 교체하며, 사용자가 추가한 비관리 파일은 보존합니다. manifest가 없는 비어 있지 않은 폴더, 출력 자체가 symlink인 경우, 저장소 루트·홈·파일시스템 루트 같은 위험 위치는 거부합니다. 테스트는 이 삭제 경계와 생성 결과의 committed byte 일치를 함께 확인합니다.

## 변경 규칙

fixture를 바꾸면 generator, manifest, 이 설명, 관련 테스트를 함께 바꿉니다. 실제 게임에서 발견한 사례를 재현해야 할 때는 원문을 복사하지 말고 의미를 제거한 최소 가상 사례를 새로 작성합니다.
