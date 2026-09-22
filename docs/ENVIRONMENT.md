# 필요한 것과 환경 준비

## 지금 필요한 것

| 구분 | 항목 | 필요 시점 |
|---|---|---|
| 저장소 | 이 GitHub 저장소 읽기·작업 브랜치 쓰기 권한 | 문서·구현 변경 |
| 실행 환경 | Python 3.11 이상, Git, 터미널, 편집기 | 로컬 개발·하네스 검사 |
| 개발 데이터 | 직접 만든 합성 스크립트·번역 fixture | TASK-002; 실제 게임 불필요 |
| 개발 도구 | Hatchling 1.x, pytest 9.x, Ruff 0.16.x 범위 | TASK-001에서 `pyproject.toml`로 확정 |
| 개인 저장 공간 | 게임 폴더·저장소와 분리된 캐시 경로 | 로컬 색인 시작 |

Python 최소 버전 선택은 표준 `tomllib`을 쓰기 위한 설계 결정입니다. 해당 모듈은 Python 3.11에 추가되었습니다([S-01](SOURCES.md)). 제품 패키지는 현재 런타임 외부 의존성이 없고, 빌드·개발 도구 범위는 `pyproject.toml`에 기록합니다.

## 실제 게임 검증 때 필요한 것

사용자가 정당하게 이용하는 Stellaris 설치본과 읽기 권한, 실제 설치 폴더, UI 또는 확인 가능한 메타데이터의 버전 정보가 필요합니다. 설치 경로를 임의로 정하지 않습니다. Steam 라이브러리는 여러 드라이브에 있을 수 있으므로 수동 경로를 v0.1의 기준 입력으로 둡니다. 전체 설치본을 채팅이나 공개 저장소에 올리지 않습니다.

사용자에게 한 번 확인할 정보: OS, 설치 방식과 폴더, 게임 버전/분기, 한국어 사용 여부, 활성 모드 유무. DLC 소유·활성 정보와 로컬 모델 사용 의향은 해당 기능을 시작할 때 확인합니다. 지금 이 정보가 없다고 문서나 합성 기반 구현을 멈출 필요는 없습니다.

## 필수가 아닌 것

Codex 사용량, 유료 모델 API, GPU, Ollama, Docker, Node.js, PostgreSQL, 벡터 DB, 클라우드 서버는 v0.1 필수가 아닙니다. 선택적 모델 단계에서는 모델별 RAM/VRAM·라이선스·다운로드 크기를 실제 선택 시 확인합니다. 특정 모델이 무료로 충분히 빠르게 동작한다고 미리 보장하지 않습니다.

## 현재 가능한 확인

저장소 루트에서 실행합니다. `python` 명령 이름은 OS 설치 환경에 따라 `python3` 또는 `py -3`일 수 있습니다.

```sh
python --version
python scripts/check_harness.py
python -m unittest discover -s tests_harness -v
```

## 구현된 개발 환경

TASK-001에서 아래 흐름을 실제 CI로 검증했습니다. 현재 CLI는 패키지 골격의 help/version만 제공하며 게임 기능은 아직 없습니다.

```sh
python -m venv .venv
# 활성화 방식은 OS에 맞게 선택
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
stellaris-supporter --help
```

가상환경 활성화를 위해 시스템 실행 정책이나 보안을 전역으로 낮추도록 요구하지 않습니다. 개발 의존성 설치에는 인터넷이 필요할 수 있습니다. TASK-001 검증은 GitHub Actions의 Ubuntu/Python 3.11.16과 Windows/Python 3.13.15에서 성공했습니다. 향후 제품의 정적 검색·회귀는 의존성을 설치한 뒤 네트워크 없이 동작해야 하며, '오프라인 런타임'과 '최초 도구 다운로드 불필요'를 혼동하지 않습니다.

## 예정 설정 계약

사용자 로컬 TOML에는 `game_root`, `data_dir`, `language`, `limits`를 둡니다. 명시 CLI 옵션 → 지정한 TOML → 안전한 기본값 순서이며 환경변수로 게임 경로를 몰래 선택하지 않습니다. `network.enabled=false`, 모델 provider는 `none`이 기본입니다. 비밀 키는 TOML 예시에 넣지 않고 후속 provider에서 환경변수 이름만 참조합니다. 실제 기본 경로와 예제 설정 파일은 TASK-003에서 Windows/Linux 테스트와 함께 확정합니다.

설치 폴더 안이나 그 상위 경로를 출력·캐시 경로로 지정하면 거부합니다. 설정 파일 위치와 데이터 폴더는 진단에서 로컬에만 표시하고 공개 보고서에서는 `<GAME_ROOT>`, `<DATA_DIR>`로 치환합니다.
