# TASK-033 — 기술 카드 정보 2안

2026-10-25, Windows 11 / Python 3.12.14 / Qt 6.12 / PyInstaller 6.22.3. 사용자가 승인한 [2안](../../docs/TECH-CARD-INFO-OPTION-2.md)의 기능 작성을 끝낸 뒤 필수 검사만 실행했다. [구조화 결과](TASK-033-tech-card-info-option-2.json).

## 결과

기술 카드에 이름, 분야/단계, 기본 연구 비용, 같은 자료의 선행 이름, 직접 명시 플래그를 표시한다. 설명은 기본으로 끄고 한국어 체크박스로 항목/순서를 선택한다. 요약 안의 스크롤을 제거하고 긴 이름·선행 목록·작은 크기를 줄 수와 추가 항목 표시로 처리한다. 편집 중 상세/관리 동작, 원문 출처, 접힌 ID/해시/진단 화면을 연결했다.

공통 변수 파일과 기술 파일 최상위 선언을 같은 스냅샷에 저장한다. 숫자/한 단계 참조만 연결하고 중복·범위 충돌·뒤에 선언된 로컬 변수·불완전 자료·수식은 확정하지 않는다. 비용의 기존 AnswerFact는 원문을 유지한다. 변수만 있는 파일도 원본 목록에 남고, 누락/추가/변경/삭제는 SID에 반영된다. 과거 카드에는 현재 설치 파일을 섞지 않는다.

기존 카드 갱신은 전후 이름/기본 비용/선행 기술 확인 후 적용한다. 중복 대상이 있으면 기존 카드 선택 또는 취소만 제공한다. UID/좌표/크기/표시 항목을 보존하고 UID/SID/정의/언어/요청 토큰이 다른 응답을 버린다. 실패 응답은 과거 정상값으로 유지하지 않는다. 게임 텍스트와 갱신 확인창은 일반 텍스트다.

## 필수 검사

| 실행 | 결과 |
|---|---|
| `python -m pytest tests/test_card_information.py tests/test_desktop.py tests/test_normative_document_integrity.py --basetemp=.venv/card-option2-final -q` | 57 passed / 110.70s |
| `python -m pytest tests/test_incremental_diff.py tests/test_disk_storage.py tests/test_answers.py tests/test_normative_document_integrity.py --basetemp=.venv/card-option2-core1 -q` | 기능 77 passed; 문서 제목 계약 1건은 기존 제목을 보존하도록 수정한 뒤 위 최종 배치에서 문서 12개 모두 통과 |
| `python -m pytest tests/test_card_information.py -k 'summary_fields or edit_actions' --basetemp=.venv/card-option2-layout-final2 -q` | 표시 항목 중복 집계 수정 후 2 passed |
| `python -m pytest tests/test_card_information.py -k 'variable_only_file or truncated_facts' --basetemp=.venv/card-option2-boundary-final -q` | 변수 전용 파일/선언 위치/64항목 밖 중복 비용 방어 2 passed |
| `python -m ruff check .` | 통과 |
| `python scripts/check_harness.py` | 원장·링크 정합성 통과; 제품 검사를 대신하지 않음 |
| `python -m build --wheel --no-isolation --outdir .venv/card-info-option2-build` | wheel 생성 |
| `python -m PyInstaller --noconfirm --clean --distpath dist/card-info --workpath build/card-info packaging/desktop.spec` | Windows 폴더 실행 파일 생성 |

초기 화면 검사는 내부 ID 표시를 전제로 했으나 새 읽기 화면은 기술명을 사용하므로 이름/기본 비용 기준으로 교정했다. 동시 실제 색인/회귀 중 첫 실행 검사가 20초 제한에 걸렸고, 대용량 작업을 마친 후 실행한 최종 배치에서는 통과했다. 타임아웃 한도를 늘려 통과시키지 않았다.

추가로 원문 출처가 목록 한도 128개를 채워도 카드 정의와 비용 변수 출처를 먼저 열 수 있도록 순서를 보장했다. `test_cost_proof_remains_reachable_when_raw_source_list_is_full` 1개 통과 후 최종 실행 파일과 wheel을 다시 만들었다.

## 실제 설치 자료와 실행 파일

별도 개인 검사 저장소에 기술·공통 변수·한영 번역 522개 파일, 번역 297,964행을 처리했다. 번역 파일 32개의 부분 분석 상태와 명시적 부분 사용 동의를 유지했다. 청색 레이저의 기본 비용 1,250, 물리학, 1단계, 선행 적색 레이저를 확인했다. 비용 원문 → 변수 선언 → 숫자에 연결된 출처 3개가 모두 일치했다. 전체 cold 실행 517.063초는 다른 검사와 동시에 실행한 값이며 성능 보장 수치가 아니다.

새 Windows 실행 파일에서 개인 검사 설정으로 `--diagnose-search`를 실행했다. 검색 2건, 카드 표시 데이터 완성, 기본 비용 1,250/출처 3개, 종료 코드 0을 확인했다. 실행 파일 안의 제품 모듈 47개가 최종 소스와 일치한다.

일반 360×260 / 작은 240×160 / 긴 한국어 제목과 다수 선행 기술의 화면을 렌더링했다. 글꼴을 먼저 등록하고 한글 glyph 누락 여부를 확인한 뒤 이미지를 확인했다. Windows 기본 글꼴 425종/한국어 107종을 사용할 수 있었으며 글꼴을 복제해 배포하지 않았다. 자체 카드 창에서 불투명도 30/90/100 각각의 보기 입력 통과/포커스 비활성 플래그, 편집 제어 표시를 확인했다. 게임에 입력을 보내는 검사는 아니다.

원문/DB/설정/이미지와 임시 실행기는 모두 무시되는 개인 검사 폴더에 있다. 기존 사용자 프로그램과 저장소는 덮어쓰지 않았다. 현재 실행 중인 기존 프로그램을 유지하기 위해 새 결과는 `dist/card-info/StellarisSupporter/StellarisSupporter.exe`에 두었다. 폴더 전체가 실행 단위다.

## 첫 적용

기존 프로그램을 종료하고 새 실행 파일을 연다. 홈에서 색인/변경 반영을 실행하고 읽은 데이터를 사용한다. 기존 카드는 고정 카드 → 최신 정의 선택·갱신에서 전후 내용을 보고 적용한다. 이전 카드는 그 전까지 원래 자료를 유지한다.

자동 검사는 별도 저장소에서 수행했다. 사용자 앱의 첫 색인/기존 카드 갱신은 사용자가 확인하기 전까지 완료로 기록하지 않는다. 이전에 사용자가 확인한 게임 입력·재실행·창 전환 결과는 보존하며, 전체 DPI/다중 모니터/종료 잔여 창 수용까지 확장하지 않는다. TASK-033은 doing, 전체 E-046/E-048 상태는 유지한다. 커밋·푸시·PR·병합·배포는 실행하지 않았다.

## 참고

- [Qt 문자 배치](https://doc.qt.io/qt-6/qtextlayout.html): 한국어 줄바꿈과 마지막 줄 생략.
- [Qt 창 입력 플래그](https://doc.qt.io/qt-6/qt.html#WindowType-enum): 카드 보기 입력 통과/포커스 비활성.
- [Qt 확인창 일반 텍스트](https://doc.qt.io/qt-6/qmessagebox.html#textFormat-prop): 자동 HTML 해석을 사용하지 않도록 명시.


## 사용자 앱 표시 확인 — 후속

사용자가 처음 보낸 화면은 기본 비용이 ‘변수 자료 없음’이었으며, 이는 이전 자료를 조회하는 legacy 상태와 일치했다. 이어서 보낸 검색/기술 상세/게임 위 카드 3개 화면에서는 모두 기본 연구 비용 1,250을 표시한다. 물리학·1단계·선행 적색 레이저, 읽을 수 있는 한글과 기술 설명, 상세의 원래 비용 표현 @tier1cost2도 확인했다. 따라서 별도 검사 저장소뿐 아니라 사용자 앱에서도 새 자료의 표시가 동작한다는 근거가 확보됐다.

이 결과는 사용자의 첨부 이미지로 확인했다. 화면 자동 조작이나 사용자 AppData를 직접 읽어 확인한 결과로 바꾸지 않는다. 변수 정의 출처를 실제로 열었는지, 새 카드를 만들었는지 기존 UID를 갱신했는지, 이전 위치/크기가 유지됐는지는 이미지에서 확정하지 않는다. 전체 DPI/다중 모니터/종료 잔여 창 상태도 유지한다. 이번 확인 중 제품 코드·실행 파일·사용자 설정을 변경하지 않았다.
