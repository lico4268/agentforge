> 📚 **낡은 설계** — [DIRECTION.md](../../../DIRECTION.md)로 대체됐다. 분기 이름·노드 역할 고정에 관한 서술은 현재 방향과 다르다. 당시 판단 근거를 찾을 때만 읽는다.

# Loop 노드 — 1급 캔버스 노드로서의 루프 제어

- **작성일**: 2026-08-07
- **상태**: 구현·검증 완료 (2026-08-08)
- **작업 스트림**: `work/radial-agent-canvas/` (Loop Control UI) 후속
- **대체하는 문서**: `docs/superpowers/specs/2026-08-06-loop-policy-design.md` (본 설계로 전면 대체 — sidecar 정책 모델과 Loop Scope Lens를 함께 폐기)
- **관련 문서**: `work/radial-agent-canvas/LOOP_CONTROL_UX_PLAN.md`, `LOOP_ENGINEERING_RESEARCH.md`, `DECISIONS.md`

## 배경

2026-08-06에 `LoopPolicy`라는 sidecar 계약(Architecture의 별도 배열, `feedbackEdgeIds`/`exitEdgeIds`로 기존 엣지를 참조)과 그 컴파일러 배선(컴파일 시점에 합성 `__loop_guard__` 노드를 끼워넣고 조건부 라우팅을 바꿔치기하는 방식)이 설계·구현됐다(커밋 `ec0f9cc`). 이 구현은 **한 번도 실행 검증되지 않은 채** 머지됐다 — `server/workspace/`의 최신 실행 기록은 7/14이고, 8/4~8/6 3일치 커밋(Loop Scope UI + LoopPolicy 백엔드)은 단위테스트·타입체크까지만 통과했다.

사용자가 대안을 제안했다: 루프 설정을 sidecar 배열이 아니라 **캔버스에 직접 그리는 노드**로 만들고, 그 노드가 "루프 도는 지점"과 "탈출하는 지점"을 자신의 출력 포트로 표현하게 하자는 것. 검토 결과 이 방향이 다음을 동시에 만족한다:

1. **복잡도 감소** — sidecar 모델이 필요로 했던 검증(엣지 참조 무결성, 단일 재진입 타깃 일치, 노드 타입 화이트리스트)이 "실제 그래프에 그려진 노드"라는 사실 자체로 구조적으로 불필요해진다.
2. **v1 제약 해제** — sidecar 설계가 비목표로 미뤄둔 "임의 노드 타입 간 cycle 일반화"가 부산물로 풀린다. Loop 노드는 자신의 입력 엣지 source가 무엇이든 상관하지 않는다.
3. **ComfyUI 철학과의 정합** — "루프가 어디서 어떻게 도는지"가 sidecar JSON이 아니라 캔버스 위에서 눈에 보인다.
4. **죽은 코드 정리** — Loop Scope Lens(Slice 7~10, SCC 기반 cycle 감지 + Tier 판별 + collapse/expand UI)가 사용자 결정으로 함께 삭제된다. 이 중 상당수(`LoopScopeNode.tsx`, `loopScopeProjection.ts` 등 6개 파일 1,065줄)는 08-05 `Replace loop scope canvas UI with anchors` 커밋 이후 이미 어디서도 참조되지 않는 고아 코드였다.

가드 평가 코어(`server/nodes/loop_guard.py`, `evaluate_loop_guard`/`next_runtime`/`GuardResult`)는 8/6 설계에서 이미 "노드 타입과 무관한 순수 함수"로 분리해뒀던 덕분에 이번 재설계에서 **한 줄도 바뀌지 않는다** — LangGraph·컴파일러 배선과 완전히 독립적으로 설계된 것이 그대로 값을 한다.

## 목표 / 비목표

**목표**
- Loop 설정(5축 guard + onExhaustion)이 sidecar가 아니라 캔버스에 그려지는 노드(`loop.guard`)의 config로 존재한다.
- 노드의 "loop back" 출력 포트와 "exit" 출력 포트가 실제 엣지로 배선되고, 그 엣지의 target이 곧 재진입/탈출 지점이다.
- 가드 없이 그려진 cycle은 컴파일 에러가 된다(sidecar 설계에서 프론트 Lens가 담당하던 "실수 방지" 역할의 이관).
- 정책 없는 기존 그래프(review.intent의 `maxRetries` 내장 로직만 쓰는 스타터 그래프 등)의 실행 결과가 유지된다.
- iteration/예산/exit reason이 WebSocket 이벤트로 노출된다(8/6 설계의 목표 유지, 필드명만 정리).

**비목표**
- Loop 노드 config를 채우는 편집 UI(폼)의 시각적 폴리시 — 기본 `GenericNode`/config 패널 생성 방식을 그대로 쓴다. 커스텀 렌더러는 만들지 않는다.
- `kind: 'retry'`(Node retry) — 8/6 설계와 동일하게 v1 대상에서 제외(`CallPolicy.retry_count`가 모델 레벨에서 이미 처리).
- 자기 자신으로 돌아오는 self-loop(단일 노드 retry)에 대한 강제 게이팅 — Loop Scope Lens에서도 별도 취급(Tier 밖)이었던 것과 동일하게, 이번 설계도 SCC 크기 ≥ 2인 cycle만 게이팅을 강제한다.

## 채택한 접근: Loop 노드 = 실행 노드 + 라우팅 오너

세 가지를 비교했다(8/6 문서의 접근 비교를 계승·수정).

| 접근 | 설명 | 비고 |
| --- | --- | --- |
| A. Sidecar + 합성 노드 삽입 (기존 8/6 설계) | Architecture의 별도 배열이 기존 엣지를 참조, 컴파일러가 라우팅을 바꿔치기 | 캔버스에 안 보임, 엣지 참조 무결성 검증이 별도로 필요, v1 노드 타입 제약 |
| **B. Loop 노드 (채택)** | `loop.guard`를 다른 노드와 동등한 1급 노드로 그린다. 출력 포트 `loopBack`/`exit`가 실제 엣지로 재진입/탈출 지점을 표현 | 캔버스에 보임, 엣지 참조 무결성이 구조적으로 보장됨, 임의 노드 간 cycle 지원 |
| C. 컨테이너형(subgraph) | Loop 노드가 본체 노드들을 감싸는 박스 | LangGraph subgraph 중첩 필요, `compile_graph`의 flat 구조 대규모 재구성 — 사용자가 게이트형을 선택하며 기각 |

B를 선택한 이유는 목표 섹션과 동일. 아래는 세부 설계다.

## 설계

### 1. 노드 계약 — `loop.guard` manifest

`server/manifests.py`의 `BUILTIN_MANIFESTS`에 추가:

```python
{
    "type": "loop.guard",
    "runtime": "loop_guard",
    "category": "policy",           # review.intent와 같은 카테고리 — 새 카테고리 불필요
    "label": "Loop",
    "description": "루프 재진입/탈출 지점과 5축 가드(iteration/token/cost/duration/stuck)를 정의.",
    "inputs": [{"id": "in", "label": "Feedback", "dataType": "any", "required": True}],
    "outputs": [
        {"id": "loopBack", "label": "Loop back", "dataType": "any"},
        {"id": "exit", "label": "Exit", "dataType": "any"},
    ],
    "config": [
        {"key": "kind", "label": "Kind", "type": "select", "default": "critiqueRevise",
         "options": [{"label": "Evaluator-Optimizer", "value": "evaluatorOptimizer"},
                     {"label": "Critique-Revise", "value": "critiqueRevise"},
                     {"label": "Human Review", "value": "humanReview"}]},
        {"key": "maxIterations", "label": "Max iterations", "type": "number"},
        {"key": "maxTokens", "label": "Max tokens", "type": "number"},
        {"key": "maxCostUsd", "label": "Max cost (USD)", "type": "number"},
        {"key": "maxDurationSec", "label": "Max duration (sec)", "type": "number"},
        {"key": "stuckWindow", "label": "Stuck window", "type": "number"},
        {"key": "stuckThreshold", "label": "Stuck threshold", "type": "number"},
        {"key": "onExhaustion", "label": "On exhaustion", "type": "select", "default": "exit",
         "options": [{"label": "Exit", "value": "exit"},
                     {"label": "Escalate", "value": "escalate"},
                     {"label": "Fail", "value": "fail"}]},
    ],
}
```

`kind`는 8/6 설계와 동일하게 **순수 서술 필드** — 컴파일러 라우팅/가드 판단에는 쓰이지 않는다(Lens가 없어졌으니 UI 표시 용도도 당장은 없지만, 추후 kind별 기본 guard 프리셋을 붙일 확장점으로 필드만 유지).

`ui/src/types/manifest.ts`의 `RUNTIMES` 튜플에 `'loop_guard'` 추가. `NodeCategorySchema`(`NODE_CATEGORIES`)는 변경 없음 — 기존 `'policy'` 카테고리를 재사용한다.

`GenericNode.tsx`는 `manifest.outputs`를 그대로 렌더링하므로(코드 주석: "Output ports always come from the static manifest definition") 2-출력 노드에 커스텀 렌더러가 필요 없다 — `review.intent`(3-출력), `human.checkpoint`(3-출력)와 동일한 경로.

### 2. 데이터 모델 — sidecar 삭제

`ui/src/types/graph.ts`에서 `ArchitectureSchema.loopPolicies` 필드, `LoopPolicySchema`, `LoopPolicyGuardSchema`를 전부 제거한다 — `GraphNodeSchema.config`가 이미 `z.record(z.string(), z.unknown())`(타입 검증 없는 record)이므로, 다른 노드 타입(예: `review.intent`의 `maxRetries`)과 마찬가지로 Loop 노드 config에도 별도 Zod 스키마가 강제되지 않는다. `LOOP_POLICY_KINDS`/`LOOP_POLICY_EXHAUSTION_ACTIONS`(문자열 배열, guard 모양과 무관)만 `loop.guard` manifest의 `kind`/`onExhaustion` select 옵션 소스로 유지한다.

`useGraphStore.ts`의 `loopPolicies` 상태 필드, `toArchitecture()`의 반영분, `starterArchitecture.ts`의 `loopPolicies: []`를 제거한다.

**마이그레이션**: `server/architectures/`에 저장된 파일이 0개이므로(실측 확인됨) 하위 호환 부담이 없다. `ArchitectureSchema`에서 필드를 제거하는 것 자체가 마이그레이션이다. `loopPolicy.schema.test.ts`의 "loopPolicies 키가 없는 기존 Architecture를 빈 배열로 채운다" 테스트는 더 이상 의미가 없으므로 삭제한다.

### 3. 컴파일러 배선 — `_prepare_loop_policies` 삭제, 노드 분기로 대체

`server/graphs/compile.py`의 `_prepare_loop_policies`(83줄, §285-367)를 전체 삭제한다. 대신 다음 흐름으로 바뀐다.

**3a. 노드 등록** — 기존 `for node in nodes:` 루프(§456)에 분기 추가:

```python
elif node_type == "loop.guard":
    outs = {e["sourceHandle"]: e["target"] for e in outgoing.get(node_id, [])}
    graph.add_node(
        node_id,
        _make_loop_guard_node(
            _loop_policy_from_config(node), node_id,
            continue_target=outs.get("loopBack"),
            exit_target=outs.get("exit"),
            emit=emit, run_id=run_id,
        ),
    )
```

`human.checkpoint`와 마찬가지로 `Command(goto=...)`로 스스로 라우팅을 결정하므로, 이후 엣지 배선 루프(§499-522)에서도 `human.checkpoint`와 동일하게 **건너뛴다**(plain edge를 추가하지 않음).

**3b. `_make_loop_guard_node` 시그니처 정리** — 기존 `policy_id` 파라미터명을 유지하되 값은 이제 실제 캔버스 `node_id`다. 함수 본문(가드 평가 호출, `Command` 반환, 이벤트 방출)은 **변경 없음** — `evaluate_loop_guard`/`next_runtime`을 그대로 호출한다.

**3c. `_loop_policy_from_config` 신설** — 노드의 평평한(flat) config를 `evaluate_loop_guard`가 기대하는 중첩 dict로 재조립하는 어댑터:

```python
def _loop_policy_from_config(node: dict) -> dict:
    cfg = node.get("config") or {}
    guard = {k: cfg[k] for k in ("maxIterations", "maxTokens", "maxCostUsd", "maxDurationSec") if cfg.get(k) is not None}
    if cfg.get("stuckWindow") is not None:
        guard["stuck"] = {"window": cfg["stuckWindow"], "threshold": cfg.get("stuckThreshold")}
    return {"id": node["id"], "onExhaustion": cfg.get("onExhaustion", "exit"), "guard": guard}
```

이 어댑터 덕분에 `server/nodes/loop_guard.py`(76줄)와 `server/tests/test_loop_guard.py`(112줄)는 **완전히 무변경**이다.

**3d. 예산 축 귀속(토큰/비용)** — 8/6 설계의 `memberNodeIds`(사용자 선언)를 **그래프 도달 가능성으로 유도**하는 것으로 대체한다: `loop.guard` 노드마다 `continue_target`에서 출발해 그 `loop.guard` 노드 자신으로 되돌아오는 도달 가능 부분집합이 루프 본체다.

```python
def _derive_loop_members(loop_node_id: str, continue_target: str | None, outgoing: dict) -> set[str]:
    if continue_target is None:
        return set()
    # continue_target에서 BFS/DFS, loop_node_id에 도달하면 그 경로 전체가 멤버
    ...
```

산출되는 `node_to_policies: dict[node_id, list[loop_node_id]]` 역인덱스는 `_make_llm_step_node`/`_make_review_node`에 지금과 동일한 방식(`loop_policy_ids` 파라미터)으로 전달된다 — 이 두 함수와 `AgentState.loop_runtime`/`merge_loop_runtime` 리듀서는 **무변경**.

### 4. 가드 없는 cycle → 컴파일 에러

Loop Scope Lens(`ui/src/canvas/loops/loopCandidates.ts`)가 담당하던 "SCC 기반 cycle 감지"를 백엔드 컴파일 검증으로 이전한다. `findStronglyConnectedComponents`(Tarjan, 45줄)를 Python으로 포팅하되, Lens가 필요로 했던 Tier 판별용 `countSimpleCyclesCapped`는 포팅하지 않는다(UI 표시 목적이 사라졌으므로).

```python
def _validate_gated_cycles(node_ids: list[str], edges: list[dict], loop_node_ids: set[str]) -> None:
    components = _tarjan_scc(node_ids, edges)  # 크기 >= 2인 컴포넌트만 cycle
    for component in components:
        if len(component) >= 2 and not (set(component) & loop_node_ids):
            raise ValueError(f"Cycle without a loop.guard node: {sorted(component)}")
```

`compile_graph`에서 `_filter_control_edges` 직후, 노드 등록 이전에 호출한다. 이로써 캔버스 경로와 향후 `/api/architectures` POST 경로 양쪽에서 강제되고, 브라우저 없이 `test_compile.py`로 검증 가능해진다(Lens는 프론트 view-layer라 vitest로만 검증됐던 것과 대비되는 개선).

**부수 효과**: `ui/src/app/starterArchitecture.ts`의 `Reasoning → Review → (refine) → Reasoning` cycle에 `loop.guard` 노드를 넣어야 컴파일이 통과한다. 스타터 그래프가 새 기능을 바로 시연하게 되므로 의도된 효과로 간주한다.

### 5. 예산 축 — 토큰/비용/시간 (8/6 설계 계승, 무변경)

- **maxIterations**: 가드 노드 진입마다 `next_runtime`이 증가.
- **maxTokens / maxCostUsd**: `run_llm_step`이 `usage_sink` out-parameter로 토큰/비용을 노출하고(이미 8/6 구현분에 있음, `compile.py:188-209` 확인됨), `_derive_loop_members` 기반 역인덱스로 루프 멤버 노드가 자기 state 업데이트에 `loop_runtime[node_id]` 증분을 얹는다.
- **maxDurationSec**: `started_at` 최초 1회 고정, 가드가 지날 때마다 `now - started_at` 계산.

### 6. Stuck 감지 (8/6 설계 계승, 무변경)

review 노드가 매 패스 "아직 unmet인 must-pass 기준 개수"를 `loop_runtime[node_id].progress_history`에 append하고, 가드는 `window` 구간 개선폭이 `threshold` 미만이면 stuck 판정(`_is_stuck`, 무변경). `humanReview` kind는 `stuckWindow`를 비워두면 자동으로 꺼진다.

### 7. 소진 처리 (`onExhaustion`, 8/6 설계 계승)

- `exit` / `escalate`: `exit_target`(`loopBack`이 아닌 `exit` 포트의 실제 엣지 target)으로 라우팅.
- `fail`: 가드 노드가 예외를 던지고, 기존 `ws_run` 에러 경로로 전파.
- 컴파일 시점 검증: `onExhaustion`이 `exit`/`escalate`인데 `exit` 포트가 배선되지 않음 → `ValueError`(§9 에러 처리).

### 8. 이벤트 계약 — 필드명 정리

8/6 설계의 `loopRuntime.loopPolicyId`를 `loopRuntime.loopNodeId`로 개명한다(영속화된 적이 없으므로 개명 비용 0). 값이 이제 실제 캔버스 `node_id`이므로, 8/6 스펙 §7이 명시했던 "프론트는 nodeId 대신 loopPolicyId로 소비해야 함(아니면 Unknown node로 렌더됨)" 특수 케이스가 사라진다 — 일반 노드와 동일하게 `nodeId` 기준으로 소비 가능해진다.

```ts
loopRuntime?: {
  loopNodeId: string
  iteration: number
  maxIterations?: number
  tokens?: number
  costUsd?: number
  durationMs?: number
  lastFeedback?: string
  exitReason?: 'success' | 'maxIterations' | 'budget' | 'stuck' | 'escalated' | 'failed'
}
```

`server/events.py`(`ExecutionEvent`)와 `ui/src/types/events.ts`(`ExecutionEventSchema`)의 필드명을 이 이름으로 맞춘다. `progress` 필드(8/6 스펙에 있던 `'converging' | 'plateauing' | 'stuck'`)는 현재 컴파일러 구현(`compile.py:390-403` 실측)에 애초에 없었으므로 이번 스펙에서도 포함하지 않는다.

### 9. 에러 처리

새 에러는 전부 `compile_graph`가 이미 쓰는 방식(`ValueError`, 컴파일 시점 즉시 실패)을 따른다.

- 가드 없이 그려진 cycle(§4) → 컴파일 에러.
- `onExhaustion`이 `exit`/`escalate`인데 `exit` 포트가 배선 안 됨 → 컴파일 에러.
- `loop.guard` 노드에 `loopBack` 포트가 배선 안 됨 → 컴파일 에러("루프가 아무 데도 안 돎"은 설정 실수).
- `onExhaustion: 'fail'` 트립 → 런타임 예외(기존 `ws_run` 에러 경로).

sidecar 설계에 있던 "feedbackEdgeIds가 존재하지 않는 엣지를 가리킴", "feedbackEdgeIds가 서로 다른 target을 가리킴" 두 에러 케이스는 **구조적으로 발생 불가능해져 삭제된다** — 엣지가 실제로 그려진 것이고, 입력 포트가 하나뿐이므로.

### 10. 삭제 목록

**이미 고아 코드(08-05 커밋 이후 어디서도 참조되지 않음, 실측 확인됨)** — 1,065줄:
- `ui/src/canvas/nodes/LoopScopeNode.tsx`, `ui/src/panels/LoopScopeInspector.tsx`
- `ui/src/canvas/loops/{tier3LoopLane,loopScopeProjection,loopScopeInspector,loopScopes,loopScopeBoundaryPorts,loopEdgeAnnotations}.ts`
- 대응 테스트: `{loopScopeProjection,loopScopeInspector,loopScopes,loopScopeBoundaryPorts,loopEdgeAnnotations}.test.ts`

**이번 결정으로 삭제(살아 있던 Lens)** — 686줄:
- `ui/src/canvas/loops/{loopCandidates,loopAnchors}.ts`
- `ui/src/panels/LoopCandidateInspector.tsx`, `ui/src/canvas/nodes/LoopAnchor.tsx`, `ui/src/canvas/LoopControlPanel.tsx`
- 대응 테스트: `loopCandidates.test.ts`, `loopAnchors.test.ts`
- `Canvas.tsx`/`Inspector.tsx`/`AgentNode.tsx`에서 이들을 참조하는 import·렌더 분기 제거

**sidecar 구현 삭제**:
- `server/graphs/compile.py`의 `_prepare_loop_policies`(83줄)
- `ui/src/types/graph.ts`의 `LoopPolicySchema` 중 엣지 참조 필드, `ArchitectureSchema.loopPolicies`
- `useGraphStore.ts`의 `loopPolicies` 상태·반영 로직
- `loopPolicy.schema.test.ts`의 마이그레이션 테스트 1건

**무변경(재사용)**:
- `server/nodes/loop_guard.py` 전체, `server/tests/test_loop_guard.py` 전체
- `run_llm_step`의 `usage_sink` out-parameter (8/6 구현분)
- `AgentState.loop_runtime` + `merge_loop_runtime` 리듀서

## 테스트 계획

1. **컴파일러**: `test_compile.py`의 `loopPolicies=[...]` 픽스처를 `loop.guard` 노드 + 실제 엣지로 교체. 기존에 검증하던 축별 트립/`onExhaustion` 3분기 의도는 그대로 유지.
2. **가드 코어**: `test_loop_guard.py` 무변경 실행 확인(회귀 없음의 증거).
3. **cycle 검증(신규)**: 가드 없는 cycle → 컴파일 에러, 가드 포함 cycle → 정상 컴파일. 기존 Lens 테스트(`loopCandidates.test.ts`)의 SCC 케이스 일부를 Python 쪽으로 이식.
4. **memberNodeIds 유도(신규)**: `_derive_loop_members`가 review→reasoning refine 루프 등에서 올바른 부분집합을 반환하는지.
5. **마이그레이션 회귀**: `loop.guard` 노드가 없는 기존 그래프(정책 없는 review.intent만 있는 경우)가 지금과 동일하게 실행되는지 — 단, §4 검증으로 인해 **가드 없는 cycle 자체가 이제 컴파일 에러**이므로, "정책 없이 실행되던 기존 스타터 그래프" 테스트는 스타터 그래프에 `loop.guard`를 추가한 버전으로 갱신해야 한다(이 테스트의 의미가 "sidecar 없어도 안전"에서 "gate 없으면 에러"로 바뀜 — §4 자체가 의도된 breaking change).
6. **이벤트**: `loopNodeId`/iteration/budget/`exitReason`이 camelCase로 정확히 직렬화되는지.
7. **프론트**: `loop.guard` manifest가 `GenericNode`로 정상 렌더(커스텀 컴포넌트 없이), config 폼이 5축 필드를 노출하는지.

## 알려진 후속 작업 (구현 단계 또는 그 이후로 이관)

- Loop 노드 config 편집 UX 폴리시(예: `stuckWindow`/`stuckThreshold`를 하나의 복합 필드로 묶어 보여주기) — 지금은 `ConfigFieldSchema`의 평평한 number 필드 두 개로 충분.
- `kind`별 guard 프리셋(예: humanReview 선택 시 stuck 필드 자동 비활성화) — v1 범위 밖.
- `_tarjan_scc`의 Python 구현이 `loopCandidates.ts`의 알고리즘과 별도 유지되는 것에 대한 장기적 중복 우려 — 현재는 언어가 다르므로(TS 프론트 vs Python 백엔드) 공유 불가능, 향후 프론트 cycle 시각화가 다시 필요해지면 재검토.
- `recursion_limit`(`cfg.MAX_RETRIES * 10 + 20`) 공식을 `loop.guard`의 `maxIterations` 합계 + 가드 hop 반영해 재검토(8/6 설계에서 이관된 미해결 항목).
