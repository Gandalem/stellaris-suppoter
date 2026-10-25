# Windows 게임 오버레이 MVP 개발 계획 (F-020)

> 사용자 승인 1안을 TASK-033에서 로컬 구현합니다. 기능 코드를 모두 작성한 뒤 필수 검사만 실행합니다. Git 통합·원격 CI·배포는 별도 요청 범위입니다. 실제 게임 수용 평가는 실행 근거로 구분합니다.

## 목표 및 비범위

Stellaris 실행 화면 위에 독립적인 Windows 오버레이를 표시합니다. 초기 검증은 Windows borderless/windowed 대상으로 하며 독점 전체 화면, Linux/macOS 오버레이는 미검증입니다. 기존 Python 서비스와 PySide6-Essentials(QtWidgets/Core/Gui)를 사용합니다. 프로세스 메모리 읽기, 게임 코드/DLL 주입, 그래픽/저수준 입력 후킹, 게임 조작, OCR, 실시간 세이브 분석은 MVP에서 제외합니다.

## 수용 조건

| ID | 동작 | 합성 검증 | 실제 Windows 수용 |
|---|---|---|---|
| OVL-01 | 단축키로 열기·접기 | 반복 입력·충돌·등록 실패·종료 시 해제 | 게임 전경에서 3회 이상 토글, 충돌 대체 조합, 포커스 확인 |
| OVL-02 | 한국어/영어 기술 검색 | 동일 pinned snapshot에서 SearchService와 결과/언어 fallback/없는 질의 일치 | 동일 검색어에 CLI/UI 결과 대조 |
| OVL-03 | 기술 정보 및 원본 출처 표시 | AnswerService의 game_id, raw_expression, relative_path, line, source hash, snapshot 및 partial/unsupported 보존 | 검증 가능한 원본 위치 수동 대조 |
| OVL-04 | 위치·크기·투명도 변경 | 값 제한·개인 설정 저장/복원·화면 좌표 복구 | 재시작, DPI/모니터 변경 후 보이는 위치 확인 |
| OVL-05 | 접힘 상태 입력 통과 | open/folded/hidden 포커스 및 이벤트 상태 | 클릭·드래그·일반 키 입력 간섭 0; 단순 alpha 0 불합격 |
| OVL-06 | 게임 종료·최소화 시 숨김 | 최소화·종료·핸들 교체·대상 식별 실패에서 fail-closed | 최소화·복원·종료 후 잔여 투명 입력 차단창 없음 |

실제 게임 창/OS 입력 동작은 자동화된 상태 모델 검사만으로 통과시킬 수 없습니다. 실기기 기록에 Windows 빌드, 게임 버전/branch 또는 unknown, 창 모드, DPI/모니터, 재현 단계, 예상/실제, 민감 정보 제거된 evidence와 실패 범위를 남깁니다.

## 데이터 및 UI 보안

오버레이는 게임과 **별도 프로세스**로 동작하고 기존 Query → SearchService → AnswerService → SnapshotRepository(개인 SQLite/cache)를 재사용합니다. 질의 시작 시 고정된 snapshot 및 출처 검증을 유지하고, 정적 필드의 미지원 표현식을 실제 엔진 계산 결과로 표시하지 않습니다. 게임/모드/번역 원문은 명령·HTML로 실행하지 않고 안전한 일반 텍스트로 표시합니다. 사용자 개인 경로는 로그·공개 스크린샷에 포함하지 않습니다. 창 설정은 게임 폴더 밖 개인 데이터입니다.

OS 수준의 단축키 등록/해제와 충돌 처리를 우선하고 저수준 키보드 후킹은 사용하지 않습니다. 접힘 상태는 완전 숨김을 우선하며 패널 유지 시 OS 수준의 **검증된 입력 통과**가 필요합니다. 게임 창 상실·최소화·종료·식별 실패·예외에서는 숨김으로 실패를 닫습니다. 창 제목만으로 프로세스를 식별하거나 보이지 않는 입력 차단면을 남기지 않습니다. 기본은 별도 서버 없는 로컬 서비스 호출이며 IPC/HTTP가 필요해지면 접근 제어와 loopback-only 및 기본 network-off 정책을 재검토합니다.

## 일정·의존성·평가

- **TASK-032 / E-048 (M2.5 선택적 기술 실험):** TASK-033의 사용자 승인 로컬 통합 범위에서 기술 후보의 단축키·입력 통과·창 추적/숨김·DPI/모니터 호환성을 Windows 실기기로 검증합니다. 정식 UI가 아니며 기존 TASK-014 및 v0.1 검증 릴리스의 게이트를 변경하지 않습니다.
- **TASK-030 / E-046 (v0.4 정식 오버레이):** TASK-033 기반 정리와 Windows 실기기 확인 뒤 OVL-01~06 전체와 검색·출처·안전성·배포 검증을 수행합니다. TASK-029 경제·전투 계산기, TASK-023~028 공지·LLM·모드·세이브 기능은 기술 검색 오버레이의 선행 조건이 아닙니다.

두 E-ID는 실제 합성 테스트와 Windows 수동 검증이 수행되어 근거가 기록되기 전에는 not_run으로 유지합니다. 미지원 화면 모드·OS와 측정되지 않은 성능을 성공으로 주장하지 않습니다.

관련 문서: [로드맵](ROADMAP.md), [요구사항](REQUIREMENTS.md), [보안](../SECURITY.md), [평가](EVALUATION.md).

## 승인 1안 구현 계약

관리창과 작은 카드 창은 같은 보조 앱 프로세스에서 실행합니다. 검색과 색인은 각각의 작업 스레드가 별도 DB 연결과 서비스를 소유합니다. 검색 결과는 요청 번호와 스냅샷에 묶이며 이전 화면 요청은 폐기합니다. 색인은 한 번에 하나만 실행하며 취소는 활성화 이전까지 전달합니다.

Steam 레지스트리 위치 → libraryfolders.vdf → appmanifest_281990.acf 순서로 설치를 찾습니다. 사용자 요청에 따라 이 읽기 전용 탐색을 허용하며 CLI의 명시적 경로 정책은 유지합니다. 여러 설치는 설정에서 선택하고 직접 게임 폴더/실행 파일을 지정할 수 있습니다. 수동 경로가 우선하며 자동 색인은 하지 않습니다. 개인 경로는 desktop.json에만 저장합니다.

오버레이 상태는 hidden/passive/interactive입니다. passive는 각 카드 창에 OS 입력 통과와 포커스 비활성 플래그를 적용합니다. Ctrl+Shift+Space는 검색·편집 전환, Ctrl+Shift+H는 완전히 숨기기입니다. 수동 숨김은 전경 변경으로 취소되지 않으며 관리창의 카드 표시 켜기 또는 검색·편집 단축키로 복구합니다. AltTab·최소화·종료·잘못된 HWND에서는 숨기고 다시 게임에 돌아오면 수동 숨김이 아닌 경우 카드 보기로만 복귀합니다.

게임의 전체 실행 경로/PID/HWND를 함께 확인합니다. 카드 좌표는 클라이언트 영역 기준의 96-DPI 좌표로 저장하고 창 DPI와 영역에 맞춰 제한합니다. 카드 종류·순서·필드·위치·크기·불투명도와 snapshot/entity를 저장합니다. 최신 정의로 갱신은 명시적 선택이며 중복 정의를 자동 결합하지 않습니다.

실행: `python -m stellaris_supporter.desktop` 또는 `stellaris-supporter-gui`. 선택 의존성은 `.[desktop]`, Windows 폴더 빌드는 `.[desktop,package]` 설치 후 `python scripts/build_desktop.py`. 결과는 dist/StellarisSupporter/StellarisSupporter.exe이며 폴더 전체가 실행 단위입니다. 실제 게임 폴더에 배치하지 않습니다.

평가 실행기는 `python -m stellaris_supporter.evaluation --output <private-report.json> --benchmark`입니다. 51개 고정 질의와 10k+중복 1개 합성 엔티티의 서비스 전체 cold/warm 시간을 기록합니다. `--suite`는 명시된 기존 합성 테스트를 실행하며 수동/다중 OS 수용과 원장 상태를 자동 승인하지 않습니다.

Qt 6.12 Windows 빌드는 Windows 기본 ICU를 사용합니다. 별도 빌드 호스트 ICU가 같은 이름으로 섞이지 않도록 packaging/desktop.spec에서 제외합니다. 근거: [Windows ICU 문서](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-). 진단용 실행 파일은 빌드에 --console을 추가합니다.

첫 실행 데이터 준비와 검색 오류 표시는 [관리창 진단 계약](DESKTOP-DIAGNOSTICS.md)을 따릅니다.


기술 카드 정보 [2안](TECH-CARD-INFO-OPTION-2.md)은 기본 연구 비용/선행 이름의 요약, 상세 출처, 한국어 표시 항목과 갱신 전후 확인을 제공한다. 이번 로컬 실행 파일은 `dist/card-info/StellarisSupporter/StellarisSupporter.exe`다. 기존 앱을 종료한 뒤 새 앱에서 한 번 색인하고, 기존 카드는 고정 카드의 최신 정의 선택·갱신으로 직접 전환한다. 같은 정의가 이미 있으면 자동 병합하지 않고 기존 카드 선택 또는 취소를 제공한다. 새 폴더는 현재 실행 중인 기존 파일을 보존하기 위해 사용했다.


[무기 부품 2안](WEAPON-COMPONENT-OPTION-2.md): 무기 검색 화면에서 계열/크기별 정의를 고르고 기본 수치·자원·조건·항목별 근거를 읽는다. 기술 상세의 관련 무기와 부품의 요구 기술/명시된 상위 부품을 같은 스냅샷으로 이동한다. 뒤로 가기는 검색·필터·선택·스크롤을 복원한다. 과거 기술 카드는 원래 자료를 유지하고 새 자료로 열기는 조회 화면만 바꾼다. 부품 고정 카드와 실전 성능 계산은 별도 범위다.

무기 2안의 최신 로컬 실행 파일은 `dist/weapons/StellarisSupporter/StellarisSupporter.exe`다. 폴더 전체를 유지한다. 기존 앱 종료 → 새 실행 파일 → 홈에서 색인 / 변경 반영 → 무기 검색 또는 기술 상세의 관련 무기 순서로 사용한다. 과거 상세는 새 자료로 보기로 조회만 전환하며 고정 카드는 명시적 갱신 전까지 기존 자료를 유지한다. [필수 검사 기록](../harness/evidence/TASK-033-weapons-option-2.md).

사용자 후속 요청으로 무기 상세의 항목별 값 근거 목록·패널·추가 근거 버튼을 제거했다. 기본 수치/자원/조건/특수 작용과 기술/상위 부품 연결을 중심으로 표시한다. 부품 정의 및 조건/특수 작용 원문 열기는 작은 목록으로 유지하고 수치 출처 데이터·검사·조회 계약은 보존한다.

값 근거 UI를 뺀 최신 실행 파일: `dist/weapons-simple/StellarisSupporter/StellarisSupporter.exe`. 기존 앱을 종료하고 이 파일을 실행하면 된다. 추가 색인 없이 기존 자료를 사용한다. [변경 기록](../harness/evidence/TASK-033-weapons-simple-ui.md).

[무기 카드 2안](WEAPON-CARD-OPTION-2.md)의 최신 로컬 실행 파일은 `dist/weapon-cards/StellarisSupporter/StellarisSupporter.exe`다. 기존 앱을 종료하고 폴더 전체를 유지한 채 실행한다. 무기 검색의 개별 무기 → 무기 카드 고정 → 편집의 연결 보기에서 기술/상위 부품을 선택해 추가 고정한다. 기존 무기 자료에 추가 색인은 필요 없다. 첫 무기 설정 저장 전 기존 설정은 별도 백업한다. [필수 확인 기록](../harness/evidence/TASK-033-weapon-cards-option-2.md).

자원 분류·변이 안내 수정 최신 파일은 `dist/weapon-data-fix/StellarisSupporter/StellarisSupporter.exe`다. 기존 앱 종료 후 새 파일을 실행하면 고정 카드도 새 표시 규칙으로 다시 읽는다. 추가 색인은 필요 없다. [수정/전체 무기 점검 결과](../harness/evidence/TASK-033-weapon-resource-fix.md).
