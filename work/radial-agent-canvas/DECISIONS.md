> 📄 **완료된 작업 기록** — 당시 진행 로그다. 현재 설계 문서가 아니며, 현재 방향은 [DIRECTION.md](../../DIRECTION.md) 참고.

# Decisions

## 확정

| 결정 | 이유 |
| --- | --- |
| 원형 노드는 UI 표현만 바꾼다. | 현재 `position`은 실행과 분리돼 있어 저장·실행 계약을 유지할 수 있다. |
| 초기 방사형 배치는 명시적 `Arrange radially` 액션으로 제공한다. | 자동 배치는 사용자가 만든 좌표를 파괴한다. |
| 원형 노드의 상세 정보는 Inspector에 둔다. | 캔버스는 역할·관계·실행 상태에 집중한다. |
| edge 화살표는 항상 실행 방향(`source → target`)을 표시한다. | 현재 모든 persisted edge는 실행 순서이고 `sourceHandle`은 분기 의미를 가진다. |
| 신규 레이아웃 의존성은 추가하지 않는다. | 순수 TypeScript BFS 기반 배치로 충분하고 롤백이 쉽다. |
| 사이클 탐지는 `LoopCandidate`만 만든다. | SCC/단순 사이클은 구조를 알려줄 뿐 retry·feedback·exit의 실행 의미를 확정하지 못한다. |
| 실행 가능한 루프는 명시적 `LoopPolicy`다. | policy ID가 guard, compiler routing, runtime event를 연결하는 안정된 키가 된다. |
| 기본 canvas는 원래 노드와 정방향 edge를 항상 보존한다. | 자동 scope 축소는 starter graph의 역할 노드를 숨겨 실행 흐름 자체를 읽기 어렵게 만들었다. |
| feedback 관계는 기본 canvas에서 짝지어진 `Loop Anchor`로 표현한다. | 길고 휘는 선 대신 source/re-entry 위치와 공통 loop ID를 보이며, 복잡성은 Loops panel과 Lens로 점진적으로 공개한다. |
| return edge의 전체 경로는 `Loop Lens`에서만 보여 준다. | 작은 국소 다이어그램은 실제 return을 설명하면서도 전체 캔버스를 혼잡하게 하지 않는다. |
| 포트 점(in/out dot)은 기본적으로 숨긴다. 방향은 edge 화살표로만 읽는다. | 사용자가 hub/rim 반구 회전을 실제로 써보고 "점이 헷갈리고 선도 겹치고 방향 파악이 안 된다"고 직접 확인(2026-08-05). 점을 없애면 경쟁할 슬롯 자체가 없어져 세 불만이 동시에 풀린다. |
| 포트 각도는 input/output 반구 구분 없이 노드 전체 360도를 공유하고, 각 포트는 실제 파트너 방향으로 편향 배치한다(겹치면 밀어냄). | 반구 구분은 "이 점이 input인지 output인지"를 위치로 표현하려던 장치였는데, 점을 안 그리면 그 구분 자체가 필요 없다. 전체 360도를 쓰면 항상 파트너를 향해 최대한 곧게 뻗을 수 있어 교차도 줄어든다. |
| 연결 포트는 `useUiStore.showConnectionPorts` 토글로만 보인다(기본 false). | 점은 새 연결을 만들 때만 필요한 편집 어포던스다 — 평소엔 숨기고 켜야 할 때만 켠다(progressive disclosure). |

## 결정 대기

1. 중심 노드: 선택 노드 우선(권장) 또는 연결 차수 자동 선택.
2. classic renderer 병행 기간: 최소 한 릴리스(권장) 또는 즉시 교체.
3. 원형 노드 지름: 112px에서 시작, 96px/128px 조정 여부.
4. checkpoint 조작: Inspector 중심(권장) 또는 원형 노드 위 inline 버튼 유지.
5. 실제 Coordinator/Tool/Memory runtime이 도입되기 전 UI에 해당 명칭을 노출할지 여부. 현재는 노출하지 않는다.
6. `LoopPolicy`를 Architecture에 저장하는 정확한 직렬화 형식과 이전 graph의 migration 방식.
7. policy별 `maxIterations`, token/cost/time budget, stuck 신호, exhaustion action의 최소 계약과 backend compiler 적용 순서.
