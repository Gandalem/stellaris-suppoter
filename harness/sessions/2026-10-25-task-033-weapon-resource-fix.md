# 2026-10-25 무기 자원 분류와 반복 안내 수정

사용자가 mult 오표시와 변이 안내 반복 수정, 추가 데이터 확인을 요청했다. 자원 제어/조건/중복 블록을 구분하고 수치 안내를 공통 요약으로 연결했다. 전체 기능 작성 후 기존 34개와 새 사례/문서 17개를 통과했다.

[결과](../evidence/TASK-033-weapon-resource-fix.md), [구조화 결과](../evidence/TASK-033-weapon-resource-fix.json). 555개 전체 점검에서 알 수 없는 자원 ID와 조회 오류는 없었다. 변이 수치 247개와 동적/조건부 비용 300개(중복 43개 포함)는 추가 해석 대상이다. 두 범위는 겹친다.

최신 실행 파일은 dist/weapon-data-fix/StellarisSupporter/StellarisSupporter.exe. 기존 자료에 추가 색인은 필요 없다. 기본 사용자 데이터·설정·기존 실행 파일은 보존하고 Git 통합은 보류했다.
