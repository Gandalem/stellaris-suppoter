# TASK-001 clean developer setup evidence

날짜: 2026-09-22  
검증 commit: `ed1e9027c0dc61c302f705443550d8d557266cc5`  
GitHub Actions: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35727223388

## 실행된 공통 단계

1. checkout
2. Python 설치
3. `python -m pip install --disable-pip-version-check -e ".[dev]"`
4. `python -m pip check`
5. package import
6. `stellaris-supporter --help`
7. `stellaris-supporter --version`
8. `python -m pytest`
9. `python -m ruff check .`
10. `python scripts/check_harness.py`

## 결과

| 환경 | job | Python | install/import/help/version | pytest | Ruff | harness |
|---|---:|---:|---|---|---|---|
| ubuntu-latest | 106743717971 | 3.11.16 | success | 22 passed | success | success |
| windows-latest | 106743718187 | 3.13.15 | success | 22 passed | success | success |

두 job 모두 최종 conclusion은 `success`였다. `pip check`도 양쪽에서 성공했다. CLI는 TASK-001 범위의 scaffold help/version만 제공한다.

## 범위와 한계

이 근거는 E-001 개발 환경 평가용이다. wheel 배포 검증(E-036/TASK-020), 실제 게임 데이터, Stellaris 호환성, parser/search 기능을 검증하지 않는다. GitHub runner의 패키지 설치에는 네트워크가 사용됐으며 이것은 향후 제품 런타임의 오프라인 동작 보장과 별개다.

로컬 컨테이너에서도 별도 clone 검증을 시도했으나 해당 실행 환경의 DNS/외부 네트워크 차단으로 GitHub clone이 불가능했다. 이를 성공 근거로 사용하지 않았고, 위의 실제 GitHub clean runner 결과만 pass 근거로 사용한다.
