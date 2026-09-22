# 출처·검증 범위

확인일: 2026-09-22. 아래는 실제 열어 확인한 기술 문서와 조회 결과입니다. 페이지 내용은 이후 바뀔 수 있으므로 구현 시 다시 확인합니다. 제품 정책·아키텍처는 이 프로젝트의 설계 선택이며 출처가 보장하는 게임 사실이 아닙니다.

| ID | 1차 출처 | 이번에 확인한 범위 |
|---|---|---|
| S-01 | [Python tomllib](https://docs.python.org/3/library/tomllib.html) | Python 3.11 도입, TOML 읽기 API; 쓰기는 별도 필요 |
| S-02 | [SQLite FTS5](https://www.sqlite.org/fts5.html) | tokenizer·trigram·query syntax; 3문자 미만 trigram full-text 제약 |
| S-03 | [Steamworks ISteamNews](https://partner.steamgames.com/doc/webapi/ISteamNews) | GetNewsForApp v2, appid/count/enddate/feeds 등; 뉴스가 모두 공식 패치라는 뜻은 아님 |
| S-04 | [Stellaris Steam 상품 페이지](https://store.steampowered.com/app/281990/Stellaris/) | Stellaris의 app ID 281990 확인; 최신 설치 버전의 증거로 사용하지 않음 |
| S-05 | [Ollama API 소개](https://docs.ollama.com/api/introduction) | 기본 로컬 API와 cloud API 구분; 모델·하드웨어·요금 선택은 이번 범위 밖 |
| S-06 | [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) | 테스트에서 환경·속성·함수 등을 대체하는 공식 API |
| S-07 | [Ruff 문서](https://docs.astral.sh/ruff/) | Python lint/format 도구 참고; 실제 의존성 버전은 TASK-001에서 검증 |
| S-08 | [Python sqlite3](https://docs.python.org/3/library/sqlite3.html) | parameter binding, 연결·트랜잭션·backup API; 최소 Python 버전에 맞는 API 선택 필요 |
| S-09 | [Python zipfile](https://docs.python.org/3/library/zipfile.html) | 후속 세이브/압축 입력의 API·제약·주의사항 참고 |
| S-10 | [actions/checkout](https://github.com/actions/checkout) | 공식 v5 ref 조회: fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 |
| S-11 | [actions/setup-python](https://github.com/actions/setup-python) | 공식 v6 ref 조회: ece7cb06caefa5fff74198d8649806c4678c61a1 |
| S-12 | [XDG Base Directory Specification 0.8](https://specifications.freedesktop.org/basedir/0.8/) | XDG_CONFIG_HOME/XDG_DATA_HOME는 절대 경로만 유효하며 unset/empty는 정의된 기본값 사용 |
| S-13 | [Python 3.13 os.access](https://docs.python.org/3.13/library/os.html#os.access) | R_OK/W_OK/X_OK 의미, access 선검사보다 EAFP 권장, access 성공이어도 실제 I/O가 실패할 수 있음 |

S-10/11은 확인한 commit에 고정하기 위한 기록이며 최신 릴리스라는 주장이 아닙니다. CI의 action 교체는 동작·권한을 재검증합니다.

## 본문을 확보하지 못한 자료

[Stellaris Modding Wiki](https://stellaris.paradoxwikis.com/Modding)와 [Localisation modding](https://stellaris.paradoxwikis.com/Localisation_modding)는 이번 열람에서 오류가 발생했습니다. 따라서 이 페이지 내용을 읽었다고 주장하거나 최신 구문·경로의 검증 근거로 사용하지 않습니다. 문서의 경로·구문 지원 범위는 합성 사례와 이후 로컬 조사로 검증할 설계입니다.

## 이번에 검증하지 않은 것

현재 공식 최신 패치 번호/코드명/출시일, 사용자의 실제 설치 버전, DLC 소유·활성 상태, 모드 로드 규칙, 세이브 필드 의미, 게임 엔진의 동적 효과·추첨·전투 결과는 검증하지 않았습니다. [불확실성 원장](UNKNOWNS.md)에 남겨 두었습니다.

외부 글을 수집할 때 원문 재배포보다 출처 URL·발행/확인 시점·필요한 짧은 근거와 요약을 우선합니다. 이용 조건·robots·접근 제한을 확인합니다. 검색 결과의 snippet만으로 게임 수치를 확정하지 않습니다.
