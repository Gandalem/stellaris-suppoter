# TASK-033 무기 카드 고정과 기술 연결 2안

2026-10-25. [승인 2안](../../docs/WEAPON-CARD-OPTION-2.md)의 전체 기능 코드를 작성한 뒤 필수 검사만 진행했다. [구조화 결과](TASK-033-weapon-cards-option-2.json). Windows 11 / Python 3.12.14 / Qt 6.12 / PyInstaller 6.22.3.

## 작성 내용

확정된 개별 무기 정의를 kind=weapon/domain=component_template 카드로 고정한다. 기존 무기 상세와 동일한 수치·자원·상태를 요약하며 피해·사거리·명중·추적·전력·제작 비용을 기본 항목으로 둔다. 피해 배율·관통·유지비·요구 기술은 선택할 수 있다. 크기·명시 계열·추가 조건/특수 작용을 구분하고 큰 숫자를 중간에서 자르지 않는다. 작은 카드에서는 계열·선택 항목부터 접고 추가 항목 수로 안내하며 공간을 늘리면 복원한다. 값 근거 패널은 복원하지 않았다.

무기 상세·개별 검색 결과·기술 상세의 개별 관련 무기·요구 기술/명시된 상위 부품 목록에서 고정한다. 연결 대상은 같은 스냅샷을 사용한다. 중복 정의는 후보를 선택하고 같은 카드 재고정은 기존 카드를 선택한다. 숨김 상태와 게임 초점을 이 동작으로 바꾸지 않는다. 카드 편집 메뉴에서 연결/상세/항목/다시 읽기/고정 해제를 사용한다. 보기에는 입력 통과·초점 비활성 창 플래그를 사용한다.

카드 창은 UID별로 재사용하고 추가/제거/갱신 대상만 조회한다. 기술·참조·변경 카드와 전체 24장 한도를 공유한다. 새 카드는 가능한 빈 영역/원본 카드 옆에 놓고 기존 카드를 이동시키지 않는다. 카드 제거·순서·항목·무기 자료 갱신은 저장 성공 후 반영한다. 기존 설정 형식과 기술 카드 기본값을 보존하고 첫 무기 설정 저장 전 원본 설정을 백업한다. 설정 경로별 짧은 잠금과 파일 digest 확인으로 중복 저장·외부 변경 덮어쓰기를 방지한다.

자료 갱신은 같은 부품 ID의 후보와 전후 수치/관계를 확인한다. 확인 중 카드/언어/설정 세대가 바뀌면 적용하지 않는다. 적용 직전 양쪽 데이터를 다시 조회해 확인한 내용과 같을 때만 UID·배치·선택 항목을 보존해 적용한다. 이미 고정된 새 정의와 자동 합치기를 하지 않는다. 늦은 응답과 카드별 읽기 실패를 분리하고 현재 수치를 이전 정상값으로 대체하지 않는다.

## 필수 검사

각 배치는 중복되므로 합산하지 않는다. 전체 기능 작성 이전에 제품 검사·빌드는 실행하지 않았다.

| 명령 | 결과 |
|---|---|
| python -m pytest tests/test_card_information.py tests/test_desktop.py tests/test_weapons.py -q --basetemp=.venv/weapon-cards-initial | 64 passed / 초기 headless 보조 객체의 새 호출 인자 미반영 1건 / 236.08s |
| python -m pytest tests/test_weapon_cards.py -q --basetemp=.venv/weapon-cards-feature1 | 12 passed / 표시 자릿수 기대 1건 / 34.41s |
| python -m pytest tests/test_weapon_cards.py tests/test_normative_document_integrity.py tests/test_card_information.py -k 'weapon or preview_collision or normative' -q --basetemp=.venv/weapon-cards-final1 | 25 passed / headless 보조 객체의 카드 목록 누락 1건 / 28.14s |
| 같은 최종 범위 --basetemp=.venv/weapon-cards-final2 | 28 passed, 27 deselected / 40.26s |
| python -m pytest tests/test_weapon_cards.py -k passive_flags -q --basetemp=.venv/weapon-cards-native-boundary | 1 passed, 15 deselected / 4.93s |

최종 새 무기 카드 사례는 17개다. 혼합 설정/백업/재시작, 저장 잠금·외부 변경·백업 실패, 종류/정의/항목 구분, 빈 영역/범위 배치, 직접 연결 고정/중복/기존 창 유지, 실패/늦은 응답/저장 취소, 긴 숫자와 생략 항목, 갱신 취소/언어 변경/확인 후 자료 변경/중복 대상, 연속 고정/24장 한도, 보기·편집 창 플래그와 좌표 변환을 다룬다.

기존 기술 갱신의 검사 보조 객체에 새 선택적 UID 인자와 카드 목록 표시 인터페이스를 반영했다. 충돌·UID/좌표/항목 보존·늦은 응답 거부의 기존 assertions는 유지했다. 새 검사에서 명중률의 기대를 원문 정밀도에 맞는 90.0%로 바꿨으며 제품의 십진 표시 규칙은 완화하지 않았다. 화면 확인에서 작은 카드가 계열명 때문에 기본 수치를 모두 접는 점을 고쳐 크기/조건을 한 줄로 묶고 계열부터 접었다.

마지막 편집 메뉴 보완 후 `python -m pytest tests/test_weapon_cards.py -k edit_menu_is_owned -q --basetemp=.venv/weapon-cards-menu-final`은 1 passed, 16 deselected / 4.62초다. 보이는 카드의 자식 메뉴만 편집 창 목록에 포함하며 관계없는 전경 창과 보기 상태에서는 포함하지 않는다. 이 변경 후 wheel/Windows 패키지를 다시 만들었다.

Qt 입력 통과/초점 플래그와 150% 배율에서 네이티브 배치 값에 배율을 한 번 적용하는 호출 경계를 확인했다. 이 사례의 Windows 호출은 stub이며 실제 게임 클릭/키 입력 검사로 기록하지 않는다. 이전 사용자가 확인한 공통 카드 입력·재시작·창 전환 관측은 보존한다.

## 실제 자료와 화면

기존 602개 파일/555개 무기 정의의 개인 검사 자료를 재사용했다. 새 색인을 하거나 기본 사용자 DB/설정을 변경하지 않았다. 소형 청색 레이저의 기본 피해 8.00–21.00, 최대 사거리 40.00, 명중률 90.00%, 추적률 50.00%, 소비 전력 7.00, 합금 제작 비용 15를 확인했다. 카드에서 같은 자료의 요구 기술과 상위 부품을 선택해 고정하고 기존 기술 카드 창이 유지되는 것을 확인했다.

기본 360×300/작은 240×160/편집 380×340/연결 목록의 4개 화면을 렌더링했다. 글꼴을 먼저 등록해 한글 glyph를 확인하고 이미지를 직접 확인했다. 기본 크기에는 여섯 항목이 보이며 작은 카드에는 피해와 추가 5항목 안내가 남는다. 혼합 카드 3장의 설정 왕복과 최초 백업을 확인했다. 고정 요청과 조회의 로컬 동기 검사 관측값은 624.083ms이며 실제 UI의 보장 응답 시간으로 사용하지 않는다.

원문·DB·설정·백업·화면은 무시되는 개인 검사 폴더에 유지했다. 공개 기록에는 요약 사실과 결과만 남겼다.

## 패키지와 첫 사용

python -m build --wheel --no-isolation --outdir .venv/weapon-cards-build 및 python -m PyInstaller --noconfirm --distpath dist/weapon-cards --workpath build/weapon-cards packaging/desktop.spec으로 wheel과 Windows 폴더 패키지를 만들었다.

개인 혼합 카드 설정으로 새 실행 파일의 --diagnose-weapon-card SMALL_BLUE_LASER와 기존 --diagnose-search를 실행했다. 모두 종료 코드 0이며 무기 카드 수치/요약과 기존 기술 검색 2건/기본 비용 1,250을 유지했다. 포함된 제품 모듈 52개가 최종 소스와 일치한다. 실행 파일과 wheel/소스 해시는 구조화 기록에 있다.

최신 로컬 실행 파일은 dist/weapon-cards/StellarisSupporter/StellarisSupporter.exe다. 폴더 전체를 유지한다. 기존 앱 종료 → 새 실행 파일 → 무기 검색에서 개별 무기 선택 → 무기 카드 고정으로 사용한다. 이전 무기 조회가 되던 자료라면 추가 색인은 필요 없다. 카드 보기/편집 전환은 Ctrl+Shift+Space이고 편집의 연결 보기에서 필요한 기술/상위 부품을 추가 고정한다.

실제 사용자 앱에서의 새 무기 카드 첫 고정과 게임 위 입력은 별도 사용 확인 범위다. 별도 검사 저장소 결과로 사용자 앱 완료를 대신하지 않는다. TASK-033 doing과 전체 E-046/E-048은 유지한다. 커밋·푸시·PR·병합·배포는 실행하지 않았고 기존 실행 파일을 덮어쓰지 않았다.

## 참고

- [Qt QLockFile](https://doc.qt.io/qt-6/qlockfile.html): 설정 경로별 짧은 잠금.
- [Qt Layout Management](https://doc.qt.io/qt-6/layout.html): 글꼴/공간에 맞는 카드 내용 배치.
- [Ruff import ordering](https://docs.astral.sh/ruff/rules/unsorted-imports/): import 정리.

최종 Ruff 및 원장/링크 검사 통과. [Qt QMenu](https://doc.qt.io/qt-6/qmenu.html)의 팝업 특성에 맞춰 편집 메뉴 소유 창 처리를 추가했고 대상 경계 검사를 통과했다.


## 사용자 앱 후속 확인

2026-10-25 사용자가 소형 X-선 레이저와 X선 안구 광선을 게임 위에 고정한 화면을 보냈고 “위치 이동도 잘되네”라고 보고했다. 실제 사용자 앱에서 새 무기 카드 표시·읽을 수 있는 한글·두 카드 동시 배치와 편집 중 위치 이동을 확인한 직접 관측으로 기록한다. 일반 무기 화면에는 피해 13.00–35.00/사거리 40.00/소비 전력 13.00, 합금 23/희귀 크리스탈 0.250이 표시됐다. 카드 크기 조절·새 카드 입력 통과·고정 해제·재실행 복원까지 개별 통과로 확대하지 않는다.

함께 보낸 변이 무기 화면에는 policy_required에 해당하는 결합 규칙 확인 필요가 수치마다 반복되고 자원 목록에 mult가 나타난다. 현재 일반/변이 수치 표를 별도로 다루는 정책과 일치하며, 변이 최종 수치를 일반 무기처럼 확정하는 지원 확대는 별도 결정이다. 설치된 해당 정의와 동적 비용 스크립트를 읽어 resources 안의 inline_script 및 비용 제어 필드 mult를 확인했다. 자원 처리 코드가 mult를 자원 이름으로 순회하는 점은 수정 대상으로 기록한다. 기존 동적 비용의 자료 확인 필요 상태를 임의 숫자나 0으로 채우지 않는다.

다음 보완 후보는 비용 제어 키의 자원 오분류 수정과 동일한 미확정 상태의 요약 표시다. 이 후속에서는 원본/현재 코드/공식 웹 자료를 읽고 기록만 했으며 제품 코드·실행 파일·사용자 설정/DB를 변경하거나 제품 검사를 반복하지 않았다.
