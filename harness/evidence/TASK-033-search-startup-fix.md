# TASK-033 — 실제 검색 복구·카드 중복/테마 수정

2026-10-25. 사용자가 문제 발생 시 인터넷 자료를 찾아 해결하도록 지시했고, 검색 오류 수정 진행을 승인했다. 작업 중 실제 카드 중복/흰 배경 화면도 제공했다. 기존 로컬 변경을 보존하고 수정 범위의 기능 코드 작성 후 필수 검사만 실행했다. 커밋·푸시·PR·병합·배포는 하지 않았다.

## 확인된 원인과 사용자 결과

실제 사용자 실행 파일의 코드가 `SNAPSHOT_NOT_READY`였고 로컬 진단의 원인은 `No active snapshot.`이었다. 조회한 논리 경로의 hash는 같지만, 에이전트가 실행한 프로세스에서는 33,927,168 bytes/partial 스냅샷 1개/활성 포인터가 있는 파일을, 사용자 앱에서는 94,208 bytes/스냅샷 0개/활성 포인터 없는 다른 파일 식별자를 보고 있었다. 에이전트 쪽에서 다시 관측해도 원래 큰 파일이었다. 이 실행 환경의 경로 분리 메커니즘까지 특정하지는 않았다.

따라서 앞서 ‘실제 사용자 저장소에 색인을 완료했다’는 안내는 부정확했다. 코드·DLL 누락이나 게임 타이틀 화면 때문에 검색이 실패한 것으로 보지 않는다. 사용자 앱에서 직접 색인을 실행했고, 미지원 일부 구문 때문에 최초 활성화가 PARTIAL_INDEX로 중단되는 단계까지 관측했다. 이후 읽은 데이터를 사용하도록 동의/재시도한 최종 앱에서 사용자가 **‘검색 결과가 나옴’**을 확인했다. 이는 사용자가 조작한 앱의 검색 복구 근거이며, 에이전트 실행 결과와 구별한다.

## 수정한 흐름

- 빈 저장소에서는 관리창/오버레이 검색 입력을 비활성화하고 홈에서 첫 색인을 안내한다. 완료 후 목록을 갱신하고 검색을 활성화한다.
- 진행 단계와 파일 수를 홈에도 표시한다. 작업 중 설정 선택을 고정해 현재 작업에 적용되는 값이 바뀐 것처럼 보이지 않게 한다.
- PARTIAL_INDEX에서는 사용자가 부분 정보/원문 보존에 동의한 경우에만 재시도하며 이미 읽은 파일 결과를 재사용한다. 취소·보안·자원 오류를 우회하지 않는다.
- 관리창과 오버레이에 오류 코드와 사용 안내를 표시한다. 오류 행은 카드 고정 대상이 아니다.
- 개인 data_dir에 최대 256KiB/이전 파일 1개로 진단 메타데이터를 기록한다. 질의·게임 원문·임의 예외 값·절대 경로를 로그 입력으로 수집하지 않는다. SQLite/SnapshotError의 제어된 설명과 경로를 뺀 프레임, 저장소 식별·크기·상태를 사용한다.
- 실행 파일의 `--diagnose-search`는 실제 GUI worker로 읽기 전용 검색 후 상태·결과 수·진단을 개인 JSON에 저장한다.

## 추가 카드 문제

사용자 화면에서 같은 기술을 반복 고정할 때 별도 카드가 계속 만들어지고, 부모 없는 카드 창에 테마가 적용되지 않아 흰 배경이 표시되는 것을 확인했다.

같은 kind/snapshot/game ID/entity/domain/before snapshot/depth는 새로 만들지 않고 기존 카드를 선택한다. 기존 좌표/크기/표시 항목은 유지한다. 다른 스냅샷·정의·관계 깊이는 서로 다른 카드다. 카드 창에 테마를 직접 적용하고 기술 제목은 검증된 표시 이름을 사용한다.

이미 저장된 중복은 고정 카드의 ‘중복 정리’에서 사용자 동의 후 정리한다. 동일 내용·동일 표시 항목만 대상으로 하고 첫 항목을 남긴다. 원래 설정은 먼저 별도 개인 JSON으로 백업한다. 백업/저장 실패 시 원래 목록을 유지하며 사용자 설정을 에이전트가 임의로 덮어쓰지 않는다.

## 실행 근거

아래 묶음은 겹치므로 합산하지 않는다.

- 초기 진단 영향 검사 `tests/test_desktop.py tests/test_retrieval.py`: **68 passed**, 102.83초.
- 초기 데이터→색인→검색 및 부분 동의/거절을 포함한 desktop 최종 묶음: **19 passed**, 64.65초.
- 카드 후속 포함 최종 `tests/test_desktop.py`: **20 passed**, 63.94초. 같은 카드를 5회 추가 고정해도 1개 유지/위치 불변, 실제 Qt palette의 어두운 배경, 정리 거절/동의, 백업을 재로딩한 원본 카드 2개 보존, 서로 다른 정의/스냅샷/깊이/표시 항목의 분리 등을 포함한다.
- `tests/test_package.py tests/test_normative_document_integrity.py`: **16 passed**, 0.98초. 카드 후속은 기존 문서의 고정된 표제를 변경하지 않았다.
- repository-wide Ruff, wheel, Windows onedir 빌드와 diff whitespace 확인 통과.
- 최종 배포 archive의 제품 모듈 **44개**를 현재 소스와 비교, 바이트코드/상수/이름/함수 플래그 차이 0.
- 갱신한 기본 실행 파일의 실제 worker 검색: 종료 0, 결과 2개, 부분 분석 상태 보존. 별도의 빈 저장소: 종료 1, 완료=true, SNAPSHOT_NOT_READY라는 예상 진단으로 정상 종료. 두 결과를 성공 검색과 혼동하지 않는다.

Windows 최종 실행 파일은 `dist/StellarisSupporter/StellarisSupporter.exe`이다. 이전 실행 파일은 ignored 개인 검사 폴더에 백업한 뒤 갱신했다. `dist/ready`는 사용자 검색 복구 확인 당시 버전이며 이후 카드 수정은 기본 경로의 최종 파일에 포함된다.

사용자가 실제 게임 위 카드 표시까지 확인했지만 최신 테마/중복 정리의 실제 조작, 게임 클릭/키 입력 통과, DPI/다중 모니터, 최소화/복원/종료 전체 수용을 통과로 기록하지 않는다. E-046/E-048 not_run 및 TASK-033 doing을 유지한다.

## 인터넷 조사

[PyInstaller 공식 진단](https://pyinstaller.org/en/stable/when-things-go-wrong.html), [windowed 환경 차이](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html), [Qt 스레드](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html), [Qt stylesheet 적용 범위](https://doc.qt.io/qt-6.12/stylesheet.html), [Windows 파일 식별](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_info)을 확인하고 실제 관측과 대조했다. 일반적인 DLL/모듈 누락 설명을 근거 없이 수정 원인으로 쓰지 않았다.

구현 계약: [관리창 진단](../../docs/DESKTOP-DIAGNOSTICS.md). 기계 결과: [JSON](TASK-033-search-startup-fix.json).


## 미리보기 글꼴 누락 확인 및 정정

사용자가 검사 이미지의 네모 글자를 지적했다. 이전 테마 확인 때 이를 놓쳤으며 글꼴이 확인됐다고 볼 수 없는 이미지였다. offscreen Qt 환경에서 font database가 0개라 한글/영문 모두 glyph를 찾지 못한 것으로 재현했다. 실제 Windows platform 경로에서는 글꼴 425개/한글 글꼴 107개가 관측됐고, 같은 한영 문장의 glyph 누락은 0이었다.

미리보기 프로세스에 설치된 Segoe UI와 Malgun Gothic을 QFontDatabase.addApplicationFont로 직접 등록한 뒤 동일 카드 이미지를 다시 렌더링했다. 한글은 Malgun Gothic, 영문은 Segoe UI로 처리됐고 glyph index 0인 문자가 없었다. 새 PNG를 눈으로 확인해 한글·영문이 정상 표시됨을 확인했다. 폰트 파일을 복제·다운로드·배포하지 않았고 제품 코드/실행 파일은 변경하지 않았다. 이는 미리보기 환경 교정이며 실제 사용자 앱에 새 폰트 패치를 적용했다고 주장하지 않는다. Qt 근거: https://doc.qt.io/qt-6/qfontdatabase.html.


## 중복·표시 재확인

사용자가 지정한 중복·표시 항목만 코드 변경 없이 재확인했다. Qt Windows platform에서 실제 색인 데이터를 조회하고 별도 검사 설정 파일에만 카드를 저장했다. 같은 기술을 11회 고정한 결과 카드/창 각 1개, 기존 UID/좌표 유지. 제목 ‘청색 레이저’, 본문 배경 #101720, 제목/본문 glyph index 0개 누락으로 확인했다. 실제 사용된 family는 Malgun Gothic/Segoe UI다. Windows 렌더링 PNG를 눈으로도 확인했다. 원래 사용자 설정과 실행 파일은 변경하지 않았다. 이 검사는 별도 소프트웨어 검사 창의 렌더링이며 사용자 게임 위 조작 확인을 뜻하지 않는다.
