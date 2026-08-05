# Loop Engineering 조사 — Loop Control 구현 근거

> 이 문서는 loop policy·compiler·runtime 설계의 기술 근거다. 화면 표현의 단일 최신 기준은 `LOOP_CONTROL_UX_PLAN.md`다.

## 핵심 결론

1. `recursion_limit`은 그래프 전체 superstep 안전 한도다. 개별 루프의 반복 한도는 state counter와 conditional route로 별도 구현해야 한다.
2. 각 루프는 성공, 최대 반복, token/cost 예산, 시간, stuck, escalation, 사용자 중단 중 하나로 반드시 탈출해야 한다.
3. 예산은 `maxIterations`, `maxTokens` 또는 `maxCostUsd`, `maxDurationSec`의 3축으로 독립 관리한다. 초과 이유를 runtime event에 명시한다.
4. 구조상 cycle이 있다고 실행 루프 정책이 자동으로 결정되지는 않는다. cycle detection은 후보이며, 실행·관측 단위는 명시적 `LoopPolicy`다.
5. runtime은 반복 횟수뿐 아니라 마지막 feedback, 누적 비용/시간, progress trend, stuck 이유, exit reason을 보내야 UI가 숫자를 추정하지 않는다.

## 1. LoopPolicy와 실행 계약

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

- `id`는 Architecture, compiler state, WebSocket event, UI selection을 연결하는 안정된 식별자다.
- `feedbackEdgeIds`는 되돌림의 실행 경로를 명시하고, `exitEdgeIds`는 정상/에스컬레이션/강제 종료 경로를 명시한다.
- cycle candidate는 사용자가 policy를 생성할 때 초깃값을 제안할 수 있지만, 정책을 자동으로 저장하거나 적용하지 않는다.
- 이전 graph에 policy가 없으면 실행 의미를 바꾸지 않고 candidate 상태로만 표시한다.

## 2. 종료와 guard

루프는 다음 중 하나라도 만족하면 탈출한다.

| 탈출 경로 | 검사 | 예시 |
| --- | --- | --- |
| Success | policy별 성공 조건 | `score >= 0.9`, `humanApproved` |
| Max iteration | policy counter | `iteration >= 5` |
| Budget exceeded | token/cost/time guard | token 또는 실행 시간 초과 |
| Stuck | 최근 progress window | 점수/상태 변화 없음, 같은 tool call 반복 |
| Escalation | 불확실성 또는 policy action | `interrupt()` 후 사람 검토 |
| Forced stop | 사용자/시스템 action | run cancel, timeout |

`recursion_limit`은 위 guard를 대체하지 않는다. 전체 그래프가 제한에 도달했다는 사실만 알려 줄 뿐, 어느 loop policy가 몇 번째 반복에서 종료돼야 하는지는 알 수 없다.

## 3. state와 conditional route

루프별 state에는 누적값과 현재 시도 값을 분리한다.

```python
class LoopRuntime(TypedDict):
    iteration: int
    total_tokens: int
    total_cost_usd: float
    started_at: float
    last_feedback: str | None
    progress_history: list[float]
```

- 누적: iteration, 시도 이력, feedback 이력, token/cost/time, 최종 output
- 현재 시도: draft, last score, last feedback
- router는 node 실행 뒤 guard를 평가해 `continue`, `success`, `budget_exceeded`, `stuck`, `escalate`, `fail` 중 하나를 반환한다.
- `onExhaustion`은 생성된 route가 어디로 갈지 결정한다. UI에서 보이는 설정은 compiler가 실제로 적용한 것과 같아야 한다.

## 4. runtime event 계약

각 루프 관련 event에는 다음 필드를 보낸다.

```ts
type LoopRuntimeEvent = {
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

- 값이 없으면 UI는 node call count 같은 간접값으로 반복 횟수를 추정하지 않는다.
- `progress`는 단순 색상이 아니라 text 상태와 함께 전달한다.
- budget과 exit reason은 정확한 정책 ID에 매핑돼야 여러 루프가 한 run에 공존할 수 있다.

## 5. stuck 감지

무한루프는 반복 횟수만으로는 충분히 잡히지 않는다. 최근 N회 window에서 다음 신호를 확인한다.

- 품질 점수의 개선이 threshold보다 작다.
- state diff가 반복해서 비어 있다.
- 동일한 tool/action과 인자가 반복된다.
- feedback 요약 또는 결과 hash가 반복된다.

stuck 감지는 `exit`, `escalate`, `fail` 중 policy action으로 이어져야 한다. runtime에는 window, 감지 사유, 마지막 유의미한 진전을 남긴다.

## 6. 루프 유형별 최소 계약

| 유형 | 핵심 state | 성공/탈출 | 캔버스 범위 |
| --- | --- | --- | --- |
| Node retry | error count, last error | success 또는 max retries | 노드 단위 |
| Evaluator–optimizer | draft, score/feedback history | score threshold, budget, escalate | 명시적 policy |
| Critique–revise | reflection memory, convergence history | approved, max iterations, stuck | 명시적 policy |
| Human review–rework | checkpoint, approval, human feedback | approved, limit, timeout | 명시적 policy + interrupt |
| ReAct tool use | action/observation history | agent end | AgentNode 내부 |

ReAct는 캔버스 feedback loop가 아니라 AgentNode 내부 실행 요약으로 다룬다. 나머지는 `LoopPolicy`가 있어야 Canvas의 Anchor, Loops panel, Lens에 실행 상태를 보인다.

## 7. 테스트 우선순위

1. compiler: policy별 feedback/exit route가 선언대로 만들어지는지
2. guard: max iteration, 각 budget 축, stuck, exhaustion action을 독립적으로 검증
3. migration: policy 없는 기존 Architecture가 기존 실행 결과를 유지하는지
4. event: loop ID와 iteration/budget/exit reason이 camelCase 계약으로 직렬화되는지
5. UI: candidate와 configured policy 구분, runtime value 없음 표시, marker keyboard 접근성

## 참고 자료

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph recursion-limit error](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT)
- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Token Budget Aware LLM Reasoning](https://arxiv.org/pdf/2412.18547)
- [Langfuse: Agent observability](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)
