# Freeform Port Connector — Design

## 배경 / 문제

`ui/src/canvas/nodes/RadialNodePorts.tsx`와 `radialPortGeometry.ts`는 연결 편집모드
(`useUiStore.showConnectionPorts`)에서 노드의 모든 포트(입력·출력)를 항상 렌더링하는 작은
원형 점(Handle)으로 표시한다. 이미 연결된 포트는 실제 파트너 방향을 따라 동적으로 위치가
계산되어 잘 동작하지만, **아직 연결되지 않은 포트**는 `resolveNodePortAngles`의 fallback —
인덱스 기반 360도 균등분배 — 로 배치된다. 이 fallback 위치는 사용자가 실제로 무엇을 향해
연결하려는지와 무관하기 때문에, 연결 편집모드를 켰을 때 노드마다 의미 없는 위치에 점이
고정되어 있는 것처럼 보이고, 그 상태에서 그린 선들이 노드를 둘러 돌아가며 서로 얽히는
원인이 된다.

핵심 지적: "포트 = 고정 슬롯"이라는 모델 자체가 문제다. 각 포트가 항상 자기 몫의 화면
위치를 예약해 두는 대신, 실제로 필요한 순간(호버·드래그)에만 나타나야 한다.

## 목표

- 연결 편집모드에서, 미연결 포트가 무의미한 fallback 위치에 항상 떠 있는 상태를 없앤다.
- 이미 연결된 포트는 색깔 있는 점 글리프를 아예 그리지 않는다 — 연결의 존재는 엣지 선이
  노드 경계에 닿는 지점만으로 표현한다.
- 미연결 포트는 노드에 마우스를 올렸을 때만, 경계를 따라 라벨 목록으로 나타난다(호버
  리빌). 포트가 1개뿐이면 목록 없이 그 자리에 라벨 하나만 나타난다.
- 각 라벨이 실제 드래그 시작점이 되어, React Flow의 기본 연결 드래그·드롭 대상 감지를
  그대로 활용한다(연결선 드래그 자체를 새로 구현하지 않는다).

## 비목표

- 엣지 경로(직선/곡선) 렌더링 방식 — 이미 완료된 edge-routing 작업(`AgentEdge.tsx`,
  `isLoopBackEdge`)은 손대지 않는다.
- `Architecture`/`toArchitecture()`/백엔드 `compile_graph` — 데이터 모델은 전혀 변경되지
  않는다. 이 작업은 순수 캔버스 뷰 레이어 재설계다.
- Loop Scope collapse/drilldown(`loopProjection.ts`)의 `viewOverride` 로직 자체 변경 —
  synthetic 포트도 동일한 `RadialNodePorts`를 통해 렌더링되므로 이 설계를 자동으로
  물려받지만, `loopProjection.ts`의 계산 로직은 바뀌지 않는다.
- classic 모드(`canvasNodeMode === 'classic'`) — 지금처럼 이 재설계 대상이 아니다.

## 아키텍처

### 1. 연결된 포트 — 순수 기하 렌더링

지금과 동일하게 `useHubRimAngles`/`resolveNodePortAngles`가 파트너 방향을 따라 정확한
경계 교차점을 계산한다. 달라지는 건 딱 하나: **그 지점에 색깔 있는 점 글리프를 그리지
않는다.** `showConnectionPorts`가 켜져 있어도 마찬가지다. Handle 자체(React Flow가 엣지
좌표 계산에 쓰는 DOM 요소)는 그 위치에 계속 존재하지만 `opacity: 0`, `pointer-events: none`
으로 항상 비가시·비상호작용 상태를 유지한다 — 엣지 선이 이미 그 지점에서 시작/끝나므로
시각적으로는 아무것도 잃지 않는다.

기존 연결을 다시 연결(reroute)하려면 엣지를 지우고 아래 방식으로 새로 그린다 — Handle을
직접 잡아 옮기는 조작은 더 이상 지원하지 않는다(연결된 포트에 상호작용 가능한 글리프가
없으므로).

### 2. 미연결 포트 — 호버 리빌 + 라벨 목록

- **평소**: 아무것도 렌더링되지 않는다. 인덱스 기반 균등분배 fallback을 제거한다.
- **노드에 마우스를 올렸을 때** (연결 편집모드에서만): 그 노드의 미연결 포트들의 위치를
  계산해 라벨과 함께 경계를 따라 펼쳐 보여준다. 위치 계산은 기존 클러스터링 개념
  (`rimAngleDeg`/`seamAngleDeg` 기준 방향)을 재사용한다 — 다만 이제는 "항상 그 자리에
  있는 고정 배치"가 아니라 "호버가 시작되는 순간 그 자리에 계산되어 나타나는 일시적
  배치"다. 같은 방향(입력/출력) 포트끼리는 하나의 자연스러운 구역에 모여 나타나고, 노드
  전체 360도에 무작위로 흩어지지 않는다.
- 포트가 1개뿐이면 목록 없이 그 포트의 라벨 하나만 나타난다 — 고를 필요가 없으므로
  바로 드래그 시작점이 된다.
- 각 라벨 항목은 실제 React Flow `<Handle>`이다. 호버 중에만 `opacity`/`pointer-events`가
  켜지고, 마우스가 벗어나면 다시 사라진다.
- 연결 드래그를 시작해 다른 노드로 다가가면, 그 대상 노드도 동일한 방식으로 자신의
  미연결 포트 라벨을 펼쳐 보여준다 — 드롭할 포트를 고를 수 있게.

### 3. React Flow 통합 — 알려진 기술적 제약

React Flow는 활성 연결 드래그 중 유효한 드롭 대상을 DOM 히트테스트로 찾는다. 완전히
`pointer-events: none`인 요소는 이 히트테스트에서 제외되므로, 다음 두 시점에는 반드시
`pointer-events: auto`로 전환되어야 한다:

1. 사용자가 노드에 마우스를 올려 그 노드의 미연결 포트 라벨이 보이는 동안(위 2번).
2. **다른 어떤 연결 드래그든 진행 중인 동안** — 드래그 시작 노드가 아닌 노드 위에서도,
   호버 없이 드래그가 지나가는 순간 드롭 가능하도록. React Flow의 연결 진행 상태
   (`onConnectStart`/`onConnectEnd` 또는 커넥션 store)를 구독해 이 상태를 판단해야 한다.

이건 설계 차원의 결정이 아니라 순수 구현 세부사항이므로, 이후 계획서(plan)에서 태스크로
명시하고 테스트로 검증한다. 여기서는 "간과하면 드래그가 되다가 안 되다가 하는 버그가
난다"는 리스크로만 기록해 둔다.

## 영향받는 파일 (참고용 — 세부 태스크 분해는 구현 계획에서)

- `ui/src/canvas/nodes/radialPortGeometry.ts` — 균등분배 fallback 로직 제거/교체, 호버
  리빌용 클러스터링 함수 추가.
- `ui/src/canvas/nodes/RadialNodePorts.tsx` — 렌더링을 "항상 그리기"에서 "호버 상태에
  따라 그리기"로 전환. 호버 상태 관리(hover state) 추가.
- 새 컴포넌트 또는 `RadialNodePorts.tsx` 내부 확장 — 라벨 목록 UI(포트 라벨 + Handle
  결합).
- `ui/src/canvas/nodes/AgentNode.tsx`, `ui/src/canvas/nodes/LoopNode.tsx` — 두 호출부
  모두 `RadialNodePorts`를 그대로 쓰므로 직접 수정은 최소화될 것으로 예상.
- 연결 진행 상태 감지를 위한 새 훅 (예: `useConnectionInProgress`) — React Flow의
  connection store를 구독.

## 테스트 전략

- `radialPortGeometry.ts`의 새 클러스터링 함수는 순수 함수이므로 기존 패턴대로
  단위 테스트(`ui/src/__tests__/radialNodePorts.test.ts` 확장).
- 호버 상태 전환(마우스 진입/이탈 시 어떤 포트가 보이는지)은 React Testing Library로
  검증 가능한 범위까지 테스트.
- 실제 드래그-드롭 연결 생성/드롭 대상 감지는 이 샌드박스에 헤드리스 브라우저가 없어
  자동 검증이 불가능하다(`CLAUDE.local.md` 기존 제약과 동일) — 사용자가 `npm run dev`로
  직접 확인해야 하는 항목으로 명시한다.

## 미해결 세부사항 (계획 단계에서 확정)

- 라벨 목록의 정확한 시각 스타일(배경, 폰트 크기, 등장 애니메이션)은 기존 카테고리
  색상 언어(`CATEGORY_META`)를 따르되, 구현 계획 작성 시 구체적 CSS 값을 정한다.
- 호버 판정 반경(노드 자체에 올렸을 때 vs 약간의 여유 반경을 둘지)은 구현하며 실측
  조정한다.
