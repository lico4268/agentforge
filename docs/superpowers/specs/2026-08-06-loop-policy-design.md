# LoopPolicy 영속화·컴파일·런타임 계약 설계

- **작성일**: 2026-08-06
- **상태**: 설계 승인됨 — 구현 계획(writing-plans) 대기
- **작업 스트림**: `work/radial-agent-canvas/` (Loop Control UI) — `HANDOFF.md` Remaining Work #1의 후속
- **관련 문서**: `work/radial-agent-canvas/LOOP_CONTROL_UX_PLAN.md`, `LOOP_ENGINEERING_RESEARCH.md`, `DECISIONS.md`(결정 대기 #6, #7)

## 배경

Agent Canvas의 Loop Anchor UI(Slice 0~10, 커밋 `979a621`~`c0ca00e`)는 완성됐지만, 실제로 루프를 제한·관측하는 백엔드 계약이 없다. 지금 캔버스에서 감지되는 루프(예: 스타터 그래프의 `Reasoning → Review → (refine) → Reasoning`)는 review.intent 노드 config에 박힌 `maxRetries` 하나로만 제한되고, 반복 횟수·토큰·비용·시간 예산·stuck 감지는 화면에 전혀 보이지 않는다(`Not available`로 명시).

이 설계는 다음 세 가지를 하나의 계약으로 정의한다.

1. **데이터**: 실행 가능한 루프 설정(`LoopPolicy`)이 어디에, 어떤 모양으로 저장되고, 기존 Architecture와 어떻게 공존하는가.
2. **실행**: 저장된 설정을 컴파일러가 어떻게 실제 라우팅에 반영하는가.
3. **관측**: 실행 중 iteration·예산·exit reason이 어떤 이벤트로 프론트에 전달되는가.

## 목표 / 비목표

**목표**
- `LoopPolicy`가 Architecture에 저장되고, 정책 없는 기존 그래프는 실행 결과가 그대로 유지된다(마이그레이션 안전).
- `maxIterations`, `maxTokens`, `maxCostUsd`, `maxDurationSec`, `stuck` 5축 가드가 실제 LangGraph 라우팅에 적용된다.
- 가드 평가 로직이 노드 타입과 분리된 재사용 가능한 확장점으로 존재해, 향후 새 loop kind나 새 가드 축이 추가돼도 컴파일러 배선을 다시 설계할 필요가 없다.
- iteration/예산/exit reason이 WebSocket 이벤트로 노출된다.

**비목표 (이번 설계 범위 밖)**
- Loop Lens에서 Candidate를 실제 `LoopPolicy`로 만드는 편집 UI(가드값 입력 폼) — Remaining Work #5.
- Loops 패널/Lens가 `loopRuntime` 이벤트를 실제로 렌더링하는 프론트 작업 — Remaining Work #5.
- `kind: 'retry'`(Node retry) — 이미 `CallPolicy.retry_count`/`fallback`(models.py)이 모델 레벨에서 처리하므로 v1 LoopPolicy 대상에서 제외.
- 임의 노드 타입 간 cycle에 대한 일반화(예: plain LLM step 노드 두 개가 서로를 참조하는 구조) — v1은 이미 conditional routing을 지원하는 `review.intent`/`human.checkpoint`의 feedback edge만 대상으로 한다. 가드 코어와 스키마는 노드 타입에 무관하게 설계되므로, 이후 새 conditional 노드 타입이 생기면 같은 검문소 팩토리를 재사용해 확장한다(아래 "확장 지점" 참고).

## 채택한 접근: 컴파일러가 끼워넣는 공용 가드 노드 (Approach B)

세 가지를 검토했다.

| 접근 | 설명 | 비고 |
| --- | --- | --- |
| A. 노드별 내장 | review.intent/human.checkpoint 각자의 실행 함수 안에서 가드 평가 | 새 loop kind마다 각 노드 구현이 가드 로직을 다시 알아야 함 |
| **B. 공용 가드 노드 (채택)** | LoopPolicy의 feedback edge마다 컴파일러가 source→target 사이에 공용 `loop_guard` 노드를 자동 삽입 | 소스 노드 타입은 LoopPolicy를 몰라도 됨. v1 구현 범위는 A와 비슷하게 작지만 확장점이 처음부터 분리돼 있음 |
| C. 정책별 서브그래프 | 각 LoopPolicy를 독립 LangGraph subgraph로 컴파일 | 가장 강력하지만 현재 flat `StateGraph` 구조(`compile_graph`)의 대규모 재구성이 필요해 과함 |

B를 선택한 이유: v1에서 실제로 가드가 걸리는 곳은 A와 마찬가지로 review.intent/human.checkpoint 둘뿐이지만, 가드 상태 갱신·이벤트 방출·`onExhaustion` 라우팅이 전부 노드 타입과 무관한 한 곳(`_make_loop_guard_node` 팩토리 + `evaluate_loop_guard` 순수 함수)에 있어, 이후 loop 엔지니어링이 새 축이나 새 kind를 제안해도 이 확장점만 넓히면 된다.

## 설계

### 1. 데이터 모델 & 마이그레이션

```ts
type LoopPolicy = {
  id: string                          // Architecture·compiler·WS event·UI selection 공유 키
  kind: 'evaluatorOptimizer' | 'critiqueRevise' | 'humanReview'   // v1은 'retry' 제외
  feedbackEdgeIds: string[]           // 되돌아가는 edge(들) — 전부 같은 target으로 모여야 함 (§3)
  memberNodeIds: string[]             // Lens/Inspector 표시 + §4 토큰/비용 귀속 대상. 그래프 라우팅(다음 목적지 결정)에는 미사용
  exitEdgeIds: string[]               // guard 트립 시 갈 edge. v1은 exitEdgeIds[0]만 사용
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

`kind`는 컴파일러의 라우팅/가드 판단에는 쓰이지 않는 순수 서술 필드다 — Lens 표시와 향후 kind별 기본 guard 프리셋(예: humanReview는 stuck 미지원) 용도로만 참조한다.

- **저장 위치**: `ArchitectureSchema`(`ui/src/types/graph.ts`)에 `loopPolicies: z.array(LoopPolicySchema).default([])` 추가.
- **백엔드**: 새 Pydantic 모델 불필요. `server/main.py`의 `save_architecture`/`get_architecture`는 지금도 Architecture를 검증 없는 raw dict로 다루고, `compile_graph`는 `architecture.get("loopPolicies") or []`로 읽기만 하면 된다 — 지금 `nodes`/`edges`를 다루는 방식과 동일.
- **마이그레이션**: 기존 저장된 Architecture JSON에는 `loopPolicies` 키가 없다. Zod `.default([])`가 빈 배열을 채우므로 별도 마이그레이션 스크립트나 `version` 필드 변경이 필요 없다 — `nodes`/`edges`가 이미 이 패턴이다. 정책이 비어 있으면 어떤 feedback edge에도 가드가 걸리지 않고, review.intent의 기존 `maxRetries`/`retries` 내장 로직만 그대로 동작한다(레이어링, 대체 아님 — 마이그레이션 안전성의 핵심).

### 2. 런타임 상태

`AgentState`에 필드를 추가한다(기존 `retries`/`review_branch`/`feedback`는 변경하지 않음 — review.intent 자체 로직이 계속 사용):

```python
class LoopRuntimeState(TypedDict):
    iteration: int
    total_tokens: int
    total_cost_usd: float
    started_at: float
    last_feedback: str | None
    progress_history: list[float]

# AgentState에 추가
loop_runtime: Annotated[dict[str, LoopRuntimeState], merge_loop_runtime]
```

여러 루프 멤버 노드가 같은 정책 id 아래 값을 동시에 더할 수 있으므로(§4), `loop_runtime`은 기본 TypedDict 필드의 "덮어쓰기" 동작 대신 **키별 병합**(토큰/비용은 합산, `progress_history`는 append, 나머지는 최신값)하는 LangGraph 커스텀 reducer(`merge_loop_runtime`)가 필요하다. 이 이름은 자리표시자이며, 정확한 구현은 구현 단계 과제로 남긴다.

### 3. 컴파일러 배선 — 검문소 삽입

`compile_graph`(`server/graphs/compile.py`)에서 노드/엣지 등록 이후, `architecture.get("loopPolicies") or []`를 순회하며:

1. 정책이 참조하는 `feedbackEdgeIds`/`exitEdgeIds`가 실제 엣지에 존재하는지 검증 (없으면 `ValueError`, 기존 "Unknown node type" 패턴과 동일).
2. `feedbackEdgeIds`가 전부 같은 `target`을 가리키는지 검증 — 다르면 `ValueError`. (한 루프의 재진입 지점은 하나뿐이라는 확정된 UX 전제와 일치.)
3. `guard_node_id = f"__loop_guard__{policy['id']}"`로 합성 노드를 `graph.add_node`에 등록. 이 노드는 캔버스에 없는(사용자가 그리지 않은) 컴파일러 전용 노드다.
4. 각 `feedbackEdgeId`가 원래 가리키던 target을, 컴파일된 그래프에서는 `guard_node_id`로 바꿔치기한다 (review.intent의 conditional mapping, human.checkpoint의 `routes` dict 양쪽에 동일하게 적용).
5. 가드 노드 자신은 `Command(goto=...)` 패턴(`make_human_checkpoint`가 이미 쓰는 방식)으로 상태 갱신과 다음 목적지 결정을 한 번에 수행한다 — 통과 시 원래 target(재진입 노드), 소진 시 `onExhaustion`에 따라 `exitEdgeIds[0]`의 target 또는 예외.

`_filter_control_edges`나 entry-node 판정 로직은 원본 Architecture 엣지만 보고 검문소 삽입 이전 단계에서 끝나므로 영향받지 않는다.

### 4. 예산 축 — 토큰/비용/시간

- **maxIterations**: 가드 노드 자신이 진입할 때마다 `loop_runtime[policyId].iteration`을 증가시킨다. 단일 writer라 병합 문제 없음.
- **maxTokens / maxCostUsd**: 지금 `run_llm_step`(server/nodes/llm_step.py)은 토큰 사용량을 계산하지만 `log` 이벤트로만 내보내고 `AgentState`에는 전혀 남기지 않는다. 이걸 가드가 쓰려면 `run_llm_step`이 사용량을 반환값에도 포함하도록 바꾸고, 컴파일 시점에 만든 `node_id → [policyId]` 역인덱스(`memberNodeIds` 기반)를 이용해 루프 멤버 노드(`_make_llm_step_node`, `_make_review_node`)가 자기 state 업데이트에 `loop_runtime[policyId].total_tokens`/`total_cost_usd` 증분을 얹어 반환한다. `cost_for_usage()`(models.py)는 이미 있으므로 비용은 토큰과 같은 경로를 탄다. 여러 노드가 같은 칸에 값을 더하는 구조라 §2의 병합 reducer가 필요하다.
- **maxDurationSec**: 누적 불필요. `loop_runtime[policyId].started_at`만 기록해두면 가드가 지날 때마다 `now - started_at`을 그 자리에서 계산해 비교한다.

### 5. Stuck 감지

`ReviewDelta`(models.py)는 confidence 회귀를 막기 위해 의도적으로 점수 필드가 없다(POLICY_REDESIGN.md). 따라서 stuck 판정은 점수 대신 **review 노드가 이미 갖고 있는 "아직 unmet인 must-pass 기준 개수"**를 진행 신호로 쓴다: review 노드가 매 패스마다 이 값을 `loop_runtime[policyId].progress_history`에 append하고, 가드는 `guard.stuck.window` 구간에서 개선폭이 `threshold` 미만이면 stuck으로 판정한다. 이 신호가 없는 kind(humanReview)는 `guard.stuck`을 설정하지 않으면 stuck 감지가 자동으로 꺼진다.

### 6. 소진 처리 (`onExhaustion`)

- `exit` / `escalate`: `exitEdgeIds[0]`의 target으로 라우팅(의미상 구분은 UI 표시용, v1 라우팅 메커니즘은 동일).
- `fail`: 가드 노드가 예외를 던진다. 지금도 노드 실패는 `main.py`의 `ws_run` 바깥 try/except가 잡아 클라이언트에 에러 이벤트로 보내는 구조라 별도 메커니즘을 만들지 않는다.

### 7. 이벤트 계약

가드 노드도 하나의 실행 노드이므로 지날 때마다 `node_start`/`node_end`를 방출한다. `ExecutionEvent`(`server/events.py`)와 `ExecutionEventSchema`(`ui/src/types/events.ts`)에 `policyDecision`/`tokenUsage`와 같은 자리로 optional 필드를 추가한다:

```ts
loopRuntime?: {
  loopPolicyId: string
  iteration: number
  maxIterations?: number
  tokens?: number
  costUsd?: number
  durationMs?: number
  lastFeedback?: string
  progress?: 'converging' | 'plateauing' | 'stuck'
  exitReason?: 'success' | 'maxIterations' | 'budget' | 'stuck' | 'escalated' | 'failed'
}
```

가드 노드의 `node_id`는 캔버스에 없는 합성 id이므로, 프론트는 이 이벤트를 `nodeId` 기준이 아니라 **`loopRuntime.loopPolicyId` 기준**으로 소비해야 한다(일반 노드로 렌더하면 "Unknown node"가 된다). 이 필드가 HANDOFF.md에 적힌 "iteration/cost/exit reason = Not available"을 실제 값으로 채우는 자리다. 필드가 optional이라 기존 이벤트 소비 코드는 영향받지 않는다.

### 8. 에러 처리

새 에러는 전부 `compile_graph`가 이미 쓰는 방식(`ValueError`, 컴파일 시점 즉시 실패)을 따른다 — 새 메커니즘을 만들지 않는다.

- `feedbackEdgeIds`/`exitEdgeIds`가 존재하지 않는 엣지를 가리킴 → 컴파일 에러.
- `feedbackEdgeIds`가 서로 다른 target을 가리킴(§3 규칙 위반) → 컴파일 에러.
- `onExhaustion`이 `exit`/`escalate`인데 `exitEdgeIds`가 비어 있음 → 컴파일 에러(소진 시 갈 곳이 없으므로).
- `onExhaustion: 'fail'` 트립 → 런타임 예외, 기존 `ws_run` 에러 경로로 전파.

### 9. 확장 지점 (향후 loop 엔지니어링 추가용)

- 새 가드 축 추가 시: `guard` 타입에 optional 필드 추가 + `LoopRuntimeState`에 대응 누적 필드 추가 + `evaluate_loop_guard` 순수 함수에 조건 추가. 컴파일러 배선(§3)이나 "어떤 노드 타입이 가드를 받는지"는 다시 건드릴 필요 없음.
- 새 conditional 노드 타입(=새 loop kind) 추가 시: 그 노드 타입의 라우팅 mapping에서 feedback edge를 `guard_node_id`로 바꿔치기하는 배선(§3 4단계)만 새로 연결하면, 가드 노드 팩토리·스키마·이벤트 계약은 그대로 재사용된다.

## 테스트 계획

1. **컴파일러**: 정책별 feedback/exit route가 선언대로 배선되는지 (`server/tests/test_compile.py` 확장).
2. **가드**: `maxIterations`·`maxTokens`·`maxCostUsd`·`maxDurationSec`·`stuck` 각 축이 독립적으로 트립되는지, `onExhaustion` 세 값이 각각 올바른 곳으로 라우팅되는지.
3. **마이그레이션 회귀**: `loopPolicies`가 없는 기존 Architecture(현재 저장된 파일 포함)가 지금과 동일하게 실행되는지 — 특히 스타터 그래프의 review→refine 루프가 정책 없이도 그대로 동작하는지.
4. **이벤트**: `loopPolicyId`/iteration/budget/`exitReason`이 camelCase로 정확히 직렬화되는지 (`server/tests/test_events.py` + `ui/src/__tests__/events.schema.test.ts`).
5. **UI 소비**는 이번 설계 범위 밖 — Remaining Work #5에서 별도 테스트.

## 알려진 후속 작업 (구현 단계로 이관)

- `run_llm_step`이 토큰/비용을 반환값에 어떻게 노출할지(반환 시그니처 변경 vs out-parameter 등)는 구현 단계에서 확정한다. out-parameter 방식을 쓰면 `baseline.py`/`treatment.py`는 전혀 건드리지 않아도 된다 — 계획 수립 시 이 방향으로 확정됨(`docs/superpowers/plans/` 참고).
- `loop_runtime` 병합 reducer의 정확한 구현(LangGraph `Annotated` 리듀서 문법).
- `recursion_limit`(`cfg.MAX_RETRIES * 10 + 20`) 공식을 정책 `maxIterations` 합계 + 가드 hop을 반영해 재검토.
