# TASK-033 — 무기 부품 조회·기술 연결 2안

2026-10-25. 사용자가 승인한 [2안](../../docs/WEAPON-COMPONENT-OPTION-2.md)의 기능 코드를 모두 작성한 뒤 필수 검사를 실행했다. [구조화 결과](TASK-033-weapons-option-2.json).

## 작성 내용

실제 weapon_component_template와 component_set을 별도로 읽고, 등록된 두 CSV만 정확한 대소문자 key로 연결한다. 일반 무기 CSV의 기본 수치를 우선한다. mutation 표는 별도 병합 규칙을 추측하지 않고 선언 자료로 보존한다. 빈 값·0·중복·지원 밖 표현·누락을 구별한다. 자원 비용/유지비는 TXT resources에서 읽으며 CSV cost를 재료 비용으로 재해석하지 않는다. 전력 부호는 설치된 게임 설명의 규칙에 따라 소비/공급으로 구분한다.

무기 검색의 계열/크기/분류와 개별 정의 선택, 기본 수치·자원·조건·특수 작용·항목별 근거 및 원문 보기를 구현했다. 검증된 component_set만 묶고 정의별 크기/ID/조건은 보존한다. 페이지 크기와 제품/행/열/셀/화면 예산을 적용한다. 출처는 CSV 셀·헤더·key와 TXT 선언/변수까지 연결한다. CSV의 크기별 피해 계수도 특수 작용으로 표시한다.

기술 상세의 관련 무기, 무기의 요구 기술 및 명시된 upgrades_to를 같은 스냅샷으로 연결했다. 뒤로 가기는 검색·필터·선택·스크롤·탭을 복원한다. 기존 기술 상세의 값 근거와 ID/자료 기준/진단은 탭으로 보존했다. 늦게 도착한 다른 자료/정의/언어/설정의 응답은 폐기한다. 새 색인 후 조회 선택은 갱신하되 사용자 선택 변경과 과거 카드/열린 상세는 보존한다. 새 자료로 보기는 조회 화면만 변경한다.

기존 합성 component_template 계약과 기술/이벤트 검색을 보존했다. 무기 중립 제품과 manifest/정의/관계는 같은 저장 트랜잭션으로 기록한다. 원본 해시·소속·정의·관계·제품 예산을 다시 확인하고 손상이나 예상 밖 entity kind를 거부한다. 미등록 CSV는 파일/크기 예산에 청구하거나 해시하기 전에 제외한다. 링크 경로 경계는 그대로 검사한다.

## 필수 검사

모든 명령은 프로젝트 가상환경에서 실행했다. Qt 검사는 offscreen을 사용했고 한글 글꼴을 등록했다. 아래 배치들은 중복되므로 합산하지 않는다.

| 실행 | 결과 |
|---|---|
| pytest tests/test_weapons.py tests/test_card_information.py tests/test_desktop.py tests/test_normative_document_integrity.py --basetemp=.venv/weapons-final-ui -q | 75 passed / 194.67s |
| pytest tests/test_inventory.py tests/test_incremental_diff.py tests/test_disk_storage.py tests/test_answers.py tests/test_cli_vertical.py --basetemp=.venv/weapons-final-core -q | 156 passed / 5 skipped / 초기 실패 2건 / 391.05s |
| pytest tests/test_cli_vertical.py -k 'partial_explicit or invalid_utf8 or installed_console' --basetemp=.venv/weapons-cli-final -q | 위 실패 원인 수정 및 인코딩 거부 추가 사례 3 passed / 13.25s |
| pytest tests/test_weapons.py --basetemp=.venv/weapons-final-feature -q | 출처 표시/저장 경계 수정 후 16 passed / 154.35s |
| pytest tests/test_weapons.py -k 'csv_change or size_scaled' --basetemp=.venv/weapons-final-boundary -q | full 재구축/CSV 변경·삭제 시 과거 자료 유지 및 크기 계수 표시 2 passed / 16.54s |
| pytest tests/test_weapons.py -k weapon_qt_navigation --basetemp=.venv/weapons-ui-confirm -q | 마지막 기술 근거/탭 복원 변경 후 1 passed / 6.94s |

최초 무기 검사에서 이름순 정렬이 크기순 정렬을 덮는 문제를 수정했다. 위 회귀의 초기 실패 2건은 손상 UTF-8을 부분 사용으로 허용하던 오래된 검사 기대와 가상환경 console 실행 경로였다. 부분 동의 검사는 복구 가능한 구문 오류로 바꾸고, 손상 인코딩은 동의 여부와 관계없이 거부하는 별도 사례를 추가했다. 제품의 인코딩 거부 규칙을 완화하지 않았다. console 검사는 프로세스 PATH에 가상환경 Scripts를 추가해 실행했다.

생략 5건은 Windows 심볼릭 링크 권한 부재 4건과 POSIX 전용 파일명 1건이다. 제품 통과로 집계하지 않는다. 렌더링 이미지에서 한글과 선택 항목의 셀/헤더/key 근거를 확인했고, 기술 상세의 과거 근거/ID 탭을 복원한 후 해당 이동 검사를 다시 실행했다.

## 실제 자료와 실행 파일

별도 개인 검사 저장소에서 602개 파일을 색인했다. 이전 522개 중 변경 없음, 무기 관련 80개 추가. 번역 297,964행과 부분 번역 파일 32개에 대한 동의를 유지했다. 무기 정의 555개를 읽었다. component_set 정의 439개는 비무기 계열도 포함하므로 무기 계열 수로 사용하지 않는다. 청색 레이저 기술의 관련 목록은 계열 3개이며 전체 자료가 완전하다고 주장하지 않는다.

소형 청색 레이저의 기본 피해 8.00–21.00, 최대 사거리 40.00, 명중률 90%, 추적률 50%, 소비 전력 7.00을 원본과 대조했다. TXT 자원은 합금 비용 15, 에너지 유지비 0.15, 합금 유지비 0.030이다. 요구 기술 청색 레이저와 명시된 상위 소형 자외선 레이저가 같은 자료 안에서 연결된다. 기술 기본 연구 비용 1,250도 유지한다. 이전 무기 없는 자료는 기술 비용 1,250을 그대로 읽고 무기 조회는 새 색인이 필요하다고 반환한다.

실제 자료 전체 실행 118.748초, 첫 관련 조회+상세 2,864.287ms, 같은 프로세스 재조회 17.013ms였다. 로컬 검사 환경의 관측값이며 보장 성능이 아니다. 검색/무기 상세/기술 상세 화면을 렌더링하고 한글 glyph와 같은 자료 이동을 확인했다. 게임에 입력을 보내는 검사는 반복하지 않았다.

최종 Ruff 검사와 원장/링크 정합성 검사는 통과했다. 정합성 검사를 제품 테스트로 집계하지 않았다. `python -m build --wheel --no-isolation --outdir .venv/weapons-build`와 `python -m PyInstaller --noconfirm --clean --distpath dist/weapons --workpath build/weapons packaging/desktop.spec`으로 wheel 및 Windows 폴더 실행 파일을 만들었다. 새 바이너리에서 개인 검사 설정으로 --diagnose-weapon SMALL_BLUE_LASER와 --diagnose-search를 실행해 각각 종료 코드 0, 무기 기본 수치/연결 2개, 기술 검색 2건/기본 비용 1,250을 확인했다. 포함된 제품 모듈 50개가 최종 소스와 일치한다. 실행 파일 SHA256과 소스/휠 해시는 구조화 결과에 기록했다.

최종 위치는 dist/weapons/StellarisSupporter/StellarisSupporter.exe이며 폴더 전체가 실행 단위다. 기존 실행 파일과 기본 사용자 저장소/설정은 덮어쓰지 않았다. 실제 사용자 앱과 검사 프로세스의 저장소가 다를 수 있으므로 개인 검사 색인을 사용자 앱 완료로 대신하지 않는다.

## 적용

기존 프로그램을 종료하고 새 실행 파일을 연다. 홈 → 색인 / 변경 반영 후 무기 검색을 사용하거나 기술 상세의 관련 무기로 이동한다. 부분 자료 사용 동의는 기존 절차를 유지한다. 이전 자료를 연 경우 새 자료로 보기로 이동할 수 있다. 과거 고정 카드는 기존 자료를 유지하며 사용자가 갱신할 때만 변경한다.

TASK-033 doing과 전체 E-046/E-048 상태를 유지한다. 이번 기능의 실제 사용자 앱 첫 색인과 화면 확인은 후속 확인 범위다. 커밋·푸시·PR·병합·배포는 실행하지 않았다. 게임 원문·개인 DB·설정·경로·이미지는 공개 자료에 넣지 않았다.

## 참고

- [Python CSV](https://docs.python.org/3/library/csv.html): 구분자/인용/행 해석.
- [Python Decimal](https://docs.python.org/3/library/decimal.html): 유한 기본 숫자와 표시 변환.
- [SQLite isolation](https://sqlite.org/isolation.html): 별도 조회 연결과 트랜잭션.
- [Qt QTreeWidget](https://doc.qt.io/qt-6/qtreewidget.html): 계열/정의 선택과 목록 표시.


## 사용자 앱 동작 확인 — 후속

2026-10-25 사용자가 새 기능에 대해 “잘작동해”라고 보고했다. 무기 조회 기능이 사용자 앱에서도 동작했다는 직접 보고로 기록한다. 검색/계열별 모든 필터/출처 열기/이력/중복 정의 등 각각의 세부 사례까지 개별 통과로 확장하지 않는다. 이번 후속에서는 제품 코드·실행 파일·사용자 저장소/설정을 변경하거나 제품 검사를 반복하지 않았다.
