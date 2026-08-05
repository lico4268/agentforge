# Loop Control UX Plan

## 상태와 결정

이 문서는 AgentForge의 루프 표현과 설정 UI에 관한 단일 최신 계획이다. 이전의 `Loop Scope` 컨테이너 자동 축소, Tier 3 outer lane, raw-view 토글 중심 설계는 더 이상 진행 방향이 아니다. 구현은 남아 있을 수 있지만, 새 UX의 기본 동작이나 데이터 모델로 간주하지 않는다.

### 목표

- 사용자는 첫 화면에서 **모든 원래 노드와 정방향 실행 흐름**을 읽을 수 있다.
- 루프는 선이 아니라 명확한 제어 관계로 인식된다.
- 감지된 사이클과 사용자가 설정한 실행 정책을 구분한다.
- 반복 수, 예산, 탈출 조건, stuck 상태를 한 곳에서 안전하게 설정하고 실행 중 확인한다.

### 비목표

- SCC 또는 사이클 탐지만으로 실행 의미를 추론하거나 정책을 자동 생성하지 않는다.
- 기본 캔버스에서 길고 굽은 feedback edge, ghost edge, scope 컨테이너, 노드 숨김을 사용하지 않는다.
- ReAct처럼 한 AgentNode 내부에서 끝나는 루프를 외부 캔버스 루프로 억지로 표현하지 않는다.

## 정보 구조

```text
Canvas        원래 노드 + 정방향 edge + Loop Anchor
Loops panel   후보 / 설정 필요 / 구성됨 / 실행 중 / 경고 목록
Loop Lens     선택한 하나의 루프를 위한 작은 국소 다이어그램
Inspector     policy, guard, runtime, trace 설정과 상세
```

Canvas는 실행 흐름 지도이고, Loops panel과 Inspector는 제어 plane이다. 한 화면에서 두 역할을 섞지 않는다.

## Canvas: Loop Anchor

### 기본 표현

feedback edge의 source와 target에 같은 ID의 짝 마커를 붙인다. 마커는 부유하는 라벨이 아니라 노드 테두리의 실제 출발/재진입 위치에 고정되는 작은 토큰이다.

```text
Reasoning ──────────────────→ Review
  [ L1 ↩ ]                     [ ↻ L1 · 2/5 ]
  re-entry anchor              feedback-source anchor
```

| 위치 | 기본 표현 | 의미 |
| --- | --- | --- |
| feedback source | cycle SVG icon + `L1` | 여기서 이 루프가 되돌아간다. |
| re-entry target | `L1` + re-entry SVG icon | 이 루프가 여기로 들어온다. |
| 다중/복잡 루프 | `↻ 2` | 한 노드에 여러 policy가 연결되며, 클릭하면 목록을 연다. |

`refine`, `retry`, `critique` 같은 긴 텍스트는 기본 마커에 넣지 않는다. 표시 공간이 작은 캔버스에서는 ID와 방향만 보이고, 조건명과 전체 경로는 tooltip, Loop Lens, Inspector에서 확인한다.

### 기하와 시각 언어

- 마커 높이는 20–24px, 클릭·키보드 focus 영역은 36–44px이다.
- 노드 테두리에서 6–8px 밖에 배치하고, 2–3px stem으로 노드에 붙어 있음을 보인다. stem만 각도를 따르고 텍스트는 항상 수평이다.
- 루프 전용 보라/인디고 색을 사용한다. 노드 타입 색과 섞지 않으며, 색만으로 의미를 전달하지 않는다.
- 같은 쪽의 마커는 최대 2개만 쌓고 나머지는 `+N`으로 집계한다.
- 축소 줌에서는 icon/색 테두리만 남기고, Loops panel에서 같은 정보를 항상 찾을 수 있게 한다.
- 구조 아이콘은 emoji가 아니라 프로젝트의 Material Symbol 또는 SVG로 통일한다.

### 상태

| 상태 | 마커 | 보조 정보 |
| --- | --- | --- |
| Candidate | 점선 `↻ L?` | “Detected loop — set policy” |
| Configured | 실선 `↻ L1` | guard가 설정됨 |
| Running | `↻ L1 · 2/5` | 현재 iteration/한도 |
| Waiting for human | `↻ L1` + waiting indicator | 승인 대기 |
| Warning | `↻ L1` + warning icon | 예산 임박·exit 미설정 |
| Stuck / exhausted | `↻ L1` + error icon | 상태명과 원인은 패널에 텍스트로 표시 |

진행 상태는 ID의 보조 정보이며, 색 변화·점멸만으로 전달하지 않는다. 모션은 150–300ms의 opacity/color transition만 사용하고 `prefers-reduced-motion`에서는 정지한다.

### 상호작용과 접근성

- 클릭 또는 Enter/Space: 해당 Loop Policy를 선택하고 Inspector의 Loop Lens를 연다.
- hover 또는 keyboard focus: 짝 Anchor와 관련 멤버 노드의 테두리만 약하게 강조한다. 긴 선을 추가로 그리지 않는다.
- Escape: selection을 해제하고 캔버스로 돌아간다.
- 예시 접근성 이름: `Loop L1, feedback from Review to Reasoning, iteration 2 of 5`.
- focus ring, `aria-pressed`, pointer/keyboard 동작은 같은 상태를 제공한다.

## Loops panel과 Loop Lens

캔버스 상단에는 `Loops 2`처럼 개수만 보여 주고, 클릭 시 Loops panel을 연다. panel은 `Candidate`, `Needs setup`, `Configured`, `Running`, `Warning` 순으로 정렬한다. Candidate에는 “정책 설정”을, Warning에는 원인과 다음 조치를 명시한다.

Loop Lens는 선택한 policy만 고립해 보여 주는 작은 다이어그램이다. 여기에서는 source → target과 return edge를 모두 표시해도 교차하지 않는다. Canvas의 반복적 선 문제를 Lens에 옮기는 것이 아니라, 작은 범위에서만 실제 경로를 설명하는 것이다.

## 실행 정책 모델

사이클 감지는 `LoopCandidate`만 만든다. 실행 가능한 루프는 사용자가 후보에서 만들거나 템플릿으로 생성한 명시적 `LoopPolicy`다.

```ts
type LoopPolicy = {
  id: string
  kind: 'retry' | 'evaluatorOptimizer' | 'critiqueRevise' | 'humanReview'
  feedbackEdgeIds: string[]
  memberNodeIds: string[]
  exitEdgeIds: string[]
  guard: {
    maxIterations?: number
    maxTokens?: number
    maxCostUsd?: number
    maxDurationSec?: number
    stuck?: { window: number; threshold?: number }
  }
  onExhaustion: 'exit' | 'escalate' | 'fail'
}
```

정책 ID는 WebSocket runtime event의 안정된 키가 된다. `recursion_limit`은 그래프 전체 안전 한도이므로 정책의 `maxIterations`와 혼동하지 않는다.

## 루프 유형별 표현

| 유형 | 캔버스 | 설정 핵심 |
| --- | --- | --- |
| Node retry | 노드에 retry token | 횟수, backoff, 최종 실패 처리 |
| Evaluator–optimizer | Anchor pair + Lens | score exit, iteration/비용/시간 예산 |
| Critique–revise | Anchor pair + Lens | memory, convergence/stuck 기준 |
| Human review–rework | Anchor pair + waiting state | escalation, resume, 최대 대기/반복 |
| ReAct tool use | AgentNode 내부 summary | 외부 canvas policy를 만들지 않음 |

## 구현 순서

1. **기존 표현의 격리** — 자동 Loop Scope projection/컨테이너와 outer lane을 기본 경로에서 제거하고, 필요하면 Debug 전용으로 제한한다. 원래 노드와 정방향 edge는 항상 렌더한다. **완료: 기본 Canvas 경로에서 제거.**
2. **정책 없는 Candidate 표시** — 기존 SCC/사이클 탐지는 후보 목록과 `↻ L?` Anchor를 만드는 read model로만 사용한다. **완료: 안정된 `L1` ID와 Candidate 목록을 구현.**
3. **Loop Anchor 컴포넌트** — anchor 배치, overflow 집계, hover/focus pairing, zoom 단계, 접근성을 구현한다. **진행 중: source/re-entry Anchor, pairing highlight, keyboard 선택 구현. overflow/zoom 축소는 후속.**
4. **Loops panel + Lens** — policy 선택, 후보에서 policy 만들기, 국소 경로 표시를 구현한다. **진행 중: Candidate 목록과 read-only Lens 구현. 정책 생성은 다음 계약 단계.**
5. **정책 계약과 컴파일** — Architecture/서버의 명시적 `LoopPolicy`, conditional route, per-loop state counter를 설계하고 함께 구현한다.
6. **Runtime 관측성** — `loopPolicyId`, iteration, guard/budget 사용량, last feedback/progress, exit reason을 event로 보내고 UI에 연결한다.

### 현재 UI 구현 범위

- Agent Canvas는 실제 노드를 그대로 렌더하고, `refine`·`retry`·`revise`·`rework`·`reject`처럼 의미가 확인된 return edge만 숨긴다. 같은 관계는 노드 테두리의 source/re-entry Anchor가 대신 표시한다.
- 우측 `Loops N` 패널은 감지된 후보를 표시하고, 선택하면 Inspector에 Candidate Lens와 감지된 transition을 연다.
- Candidate는 아직 실행 설정이 아니다. `maxIterations`, 예산, stuck, runtime iteration을 입력하거나 표시하지 않으며, 값은 LoopPolicy/runtime 계약 구현 뒤에만 연결한다.

## 수용 기준

- starter graph의 Reasoning과 Review를 포함해 어떤 원래 노드도 루프 표현 때문에 숨겨지지 않는다.
- 보통 줌의 캔버스에서 feedback edge를 그리지 않아도 source·target·같은 loop ID를 1초 안에 식별할 수 있다.
- 복잡한 SCC는 불필요한 다수 마커 대신 집계 token과 Loops panel로 확장된다.
- Candidate와 Configured policy가 시각적으로, 데이터 모델상으로 모두 구분된다.
- iteration·비용·시간·stuck 상태는 실제 runtime event가 없으면 추정하지 않고 `Unavailable`로 명시한다.
- 마커는 마우스, 키보드, screen reader에서 같은 정보를 제공하고, reduced-motion에서도 상태를 읽을 수 있다.

## 근거

- `LOOP_ENGINEERING_RESEARCH.md`: per-loop counter, 3축 budget, progress/stuck 관측, 루프 유형별 제어 구조
- UI 검토: 캔버스는 flow map, 정책은 control plane으로 분리하고 progressive disclosure를 사용한다.
