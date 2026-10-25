# TASK-033 — 관리창·카드 오버레이 1안 로컬 근거

2026-10-21 / self_review / task/desktop-overlay-option-1 / 기준 HEAD dc6f031c1eca781b53ad224bc5c881cc01465938 + 커밋하지 않은 로컬 변경.

## 구현

기존 Python snapshot 서비스를 재사용한다. Qt 관리창(홈·기술·참조·변경 비교·카드·설정), 별도 작은 카드 창, hidden/passive/interactive 상태, 정확 실행 경로/PID/HWND, RegisterHotKey 충돌/해제, 클라이언트/DPI 좌표, 카드 원래 snapshot/entity/조회 깊이 보존과 명시적 최신 정의 선택, worker 단일 DB 소유·중복 색인 방지·취소·오래된 응답 폐기를 연결했다.

사용자 추가 승인대로 Steam 레지스트리/라이브러리/281990 manifest를 읽어 설치를 찾는다. 로컬 실제 탐색 결과 1개이며 사용자가 제공한 설치와 일치했다. 실제 경로는 공개 근거에 기록하지 않는다. 수동 설정 우선이며 자동 색인하지 않는다. 게임 원문/세이브/설정은 변경하지 않았다. 게임 실행·메모리 읽기·주입은 수행하지 않았다. 제품 코어 흐름은 socket 차단 상태에서 확인했다. 개발 의존성 설치와 공식 문서 조회는 개발 준비로 별도 수행했다.

전체 기능 코드를 먼저 작성한 다음 검사를 시작했다. 커밋·푸시·PR·병합·원격 CI·릴리스/배포는 실행하지 않았다. 이전 TASK-015/016 사용자 변경을 보존했다.

## 실제 실행한 검사

- 초기 `pytest tests/test_desktop.py`: 15 passed / 8.97s.
- 영향 검사 `tests/test_answers.py tests/test_cli_vertical.py tests/test_incremental_diff.py tests/test_desktop.py tests/test_package.py tests/test_normative_document_integrity.py`: 157 passed, 1 failed / 170.55s. 실패는 F-020=planned를 고정하던 과거 문서 조건이었다. 사용자 승인된 TASK-033 상태와 실제 게임 수용 조건을 보존하도록 갱신했다.
- 해당 문서 전체 재검사: 12 passed / 0.07s.
- geometry 저장 수정 후 desktop+문서: 27 passed / 8.59s.
- 최종 참조 깊이/오프라인 흐름/오류 비식별 추가 검사: 27 passed, 1 failed / 8.58s. 새 테스트의 json import 누락만 수정, 해당 검사 1 passed / 0.27s. 중첩되는 배치 수를 합산하지 않는다.
- 변경 Python의 Ruff 통과. check_harness 통과(문서 정합성 검사이며 제품 검사를 대신하지 않음).
- 오프라인 socket 차단 중 색인/검색/답변/참조/비교/목록 및 취소 경로 실행; 기존 합성 원문 bytes 유지, 취소 시 이전 active 유지. instruction-like 텍스트는 일반 텍스트로 유지. worker의 민감 예외 메시지는 공개 오류 코드에 포함되지 않음.

재현 명령(선택 의존성 설치 후):

```powershell
$env:PYTHONUTF8='1'
python -m pytest tests/test_desktop.py tests/test_normative_document_integrity.py --basetemp .venv/<새-검사-폴더>
python -m ruff check src/stellaris_supporter/desktop src/stellaris_supporter/evaluation.py src/stellaris_supporter/cli_index.py src/stellaris_supporter/answers.py tests/test_desktop.py scripts/build_desktop.py scripts/desktop_entry.py scripts/native_desktop_smoke.py
python -m stellaris_supporter.evaluation --output .venv/report.json --benchmark --work-dir .venv
python scripts/native_desktop_smoke.py
python -m build --wheel --no-isolation
python scripts/build_desktop.py
```

## 검색 평가와 성능

[원시 JSON](TASK-033-search-benchmark.json). 작성된 질의 51개, 질의/언어 조합 44개. ID/한국어/영어/정규화/없는 질의/두 글자 한국어 각 8개와 중복 정의·영문 정규화 3개. 두 글자 항목에는 반복 질의가 포함된다. 동일 gold를 두 번 실행해 같은 결과를 확인했다. recall@5, exact first, correct abstention 각 1.0. E-034는 로컬 합성 실행기/gold 범위 통과이며 기존 E-ID를 실행 없이 일괄 승인하지 않는다. `--suite`는 기존 자동 합성 파일 매핑을 명시적으로 실행하는 별도 선택이다.

합성 기술 10,000개+중복 정의 1개, Windows 11 build 26200 / Python 3.12.14 / SQLite 3.53.1 / 16 logical CPU / RAM 34281668608 bytes. 색인 34.118s. 새 SearchService/projection cold 5회 p95 18800.0205ms, 같은 service warm 30회 p95 8.9655ms. OS 파일 캐시를 비운 측정은 아니다. 프로세스 peak working set 119881728 bytes. 최초 projection 준비 지연은 남아 있으며 warm 500ms 목표와 구분한다. 측정 중 Qt 패키지 빌드가 일부 겹쳤으므로 전용 성능 환경의 보장값으로 사용하지 않는다.

## 패키지/Windows 창

wheel 빌드 성공. 새 Windows venv에 wheel을 `--no-index --no-deps`로 설치하고 pip check 및 init→index→search→show→refs→diff→snapshots 통과. CLI 출력 수집의 첫 시도는 UTF-8 환경 미설정으로 decoding 실패, CI와 같은 PYTHONUTF8=1을 적용한 새 fixture 흐름에서 통과했다. 기본 CLI 런타임 의존성은 0개다.

PySide6-Essentials 6.12.0/shiboken6 6.12.0/PyInstaller 6.22.3로 Windows 실행 폴더를 만들었다. 최초 frozen 실행은 빌드 호스트 ICU DLL 충돌로 실패했다. 별도 진단 console 빌드로 추적하고 packaging/desktop.spec에서 충돌 ICU를 제외한 뒤 Windows 기본 ICU로 정상 실행했다. 수정된 windowed 실행 파일의 offscreen 및 windows 플랫폼 `--smoke` 시작·종료 모두 exit 0. 실행 파일은 배포하지 않은 로컬 산출물이다.

`native_desktop_smoke.py`의 실제 Windows 자체 창에서 full path/PID/HWND 식별, 2개 창 모호성 거절, WS_EX_TRANSPARENT/NOACTIVATE 설정·해제, 단축키 충돌/해제 후 재등록, 최소화 시 대상 상실을 확인했다. 현재 DPI=144. 실제 클릭/키 입력 통과, 실제 Stellaris 화면, 다중 모니터 이동 수용을 대신하지 않는다.

Windows 화면 조작 도구는 초기화 두 번 모두 sandbox ACL 오류(helper_sandbox_lock_failed / SetNamedSecurityInfoW error 5)로 시작되지 않았다. 이를 우회한 외부 UI 자동화를 실행하지 않았다. 따라서 실제 게임 OVL-01..06 및 E-048/E-046은 not_run으로 유지한다. Linux clean package/remote CI는 실행하지 않아 E-036도 전체 통과로 올리지 않는다.

## 원장

TASK-017/018/019 로컬 합성 기반 범위는 완료, E-032/033/034/035 pass. TASK-020 전체 양 OS 수용과 TASK-032/030 실제 게임 수용은 남아 있다. TASK-033은 기능 코드 작성 100%와 로컬 필수 근거를 보존하면서 이 잔여 수용 때문에 doing으로 유지한다. F-013/014/020은 모든 연결 수용 전 verified로 올리지 않는다.


## 최종 기록

다중 Steam 설치의 첫 항목 선택/참조 깊이 보존을 포함한 최종 desktop 16개는 모두 통과했다. 마지막 desktop+문서 배치 26 passed, 2 failed / 8.98s의 실패는 추가 설명의 제목을 고정하던 문서 구조 조건이었다. 기존 제목 구조를 유지하는 설명 문단으로 정리한 후 문서 전체 12 passed / 0.05s. 제품 기능 실패가 남은 상태로 완료 처리하지 않았다. 최종 Ruff/check_harness/git diff --check 통과. 마지막 wheel/Windows onedir 빌드 성공, 최종 Windows 플랫폼 smoke exit 0, 최종 wheel clean 설치/버전 확인 통과. 양 OS/실게임 수용은 앞서 명시한 상태를 유지한다.

로컬 산출물 식별(배포 아님):

```json
{
  "dist/StellarisSupporter/StellarisSupporter.exe": {
    "bytes": 2089703,
    "sha256": "f4b26b053c46bc27317264195d0376e3cf46dc1e11118d865ddb8eb7f0150ba9"
  },
  "dist/stellaris_supporter-0.0.1-py3-none-any.whl": {
    "bytes": 150475,
    "sha256": "85117ca2ccfa71496300f5541fc7cb4ed325c6c190924576ac0c62dfb94b3b4a"
  }
}
```
