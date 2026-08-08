"""
compile_graph: 캔버스에서 직렬화된 Architecture(dict)를 실행 가능한 LangGraph
StateGraph로 컴파일한다. v0.1의 고정 그래프(baseline.py/treatment.py) 디스패치를
대체하는 v0.3 seam — dispatch_graph가 'gsm8k-baseline'/'gsm8k-treatment' 외의
아키텍처 이름을 여기로 폴백한다.
"""

import time
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import config
from events import EventEmitter, make_event
from manifests import BUILTIN_MANIFESTS
from models import CallPolicy, Criterion, ModelSettings, PlanOut, ReasonOut, build_model
from nodes.checkpoint import make_human_checkpoint
from nodes.llm_step import run_llm_step
from nodes.loop_guard import evaluate_loop_guard, next_runtime
from nodes.policy import make_route_review
from nodes.review import make_review
from state import AgentState

MANIFESTS_BY_TYPE = {m["type"]: m for m in BUILTIN_MANIFESTS}

# type -> (output_model, extra_inputs, to_state_updates, to_event_output)
LLM_STEP_TABLE: dict[str, dict[str, Any]] = {
    "planning.decompose": {
        "output_model": PlanOut,
        "extra_inputs": [],
        "to_updates": lambda result, state: {"plan": result["steps"]},
        "to_event_output": lambda result: {"plan": result["steps"]},
    },
    "reasoning.cot": {
        "output_model": ReasonOut,
        "extra_inputs": [("feedback", "Previous Feedback")],
        "to_updates": lambda result, state: {
            "answer": result["answer"],
            "confidence": result["confidence"],
        },
        "to_event_output": lambda result: {
            "answer": result["answer"],
            "confidence": result["confidence"],
        },
    },
}

PASSTHROUGH_TYPES = {"io.input", "io.output", "model.binding"}


def _make_passthrough_node(
    node_id: str,
    node_type: str,
    node_config: dict,
    emit: EventEmitter,
    run_id: str,
):
    async def passthrough(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        output = None
        updates: dict = {}
        if node_type == "io.input":
            sample = node_config.get("sample")
            if sample:
                updates["task"] = sample
                output = {"task": sample}
        elif node_type == "io.output":
            output = {"answer": state.get("answer"), "review": state.get("review_delta")}
        await emit(make_event(run_id, node_id, "node_end", output=output))
        return updates

    return passthrough


def _resolve_model(node: dict, default_model_cfg: dict):
    """slot override → 모델 기본값(config.yaml) → 전역 기본값 순으로 해석해
    (BaseChatModel, CallPolicy) 반환. modelSlots[0]만 실행 모델로 사용 (현재 제약).
    """
    slots = (node.get("config") or {}).get("modelSlots") or []
    slot = slots[0] if slots else None
    if slot:
        settings, policy = _settings_from_slot(slot)
    else:
        settings, policy = _settings_from_default(default_model_cfg)
    return build_model(settings), policy


def _coalesce(*vals):
    """첫 non-None 값. (주의: 0/False 도 유효값이므로 None 검사만 한다.)"""
    for v in vals:
        if v is not None:
            return v
    return None


def _coerce_int(*vals) -> int | None:
    for v in vals:
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return None


def _coerce_float(*vals) -> float | None:
    for v in vals:
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return None


def _fallback_settings(fb: dict | None) -> ModelSettings | None:
    if not fb or not fb.get("model"):
        return None
    return ModelSettings(
        provider=fb.get("provider", "google"),
        model=fb["model"],
        temperature=float(_coerce_float(fb.get("temperature"), 0.0) or 0.0),
    )


def _settings_from_slot(slot: dict) -> tuple[ModelSettings, CallPolicy]:
    provider = slot["provider"]
    model = slot["model"]
    md = config.model_defaults(model)
    settings = ModelSettings(
        provider=provider,
        model=model,
        temperature=float(_coerce_float(slot.get("temperature"), md.get("temperature"), 0.0)),
        max_tokens=_coerce_int(slot.get("maxTokens"), md.get("max_tokens")),
        top_p=_coerce_float(slot.get("topP"), md.get("top_p")),
        stop=[s for s in (slot.get("stopSequences") or []) if s] or None,
        seed=_coerce_int(slot.get("seed")),
    )
    policy = CallPolicy(
        timeout_seconds=float(_coerce_float(slot.get("timeoutSeconds"), config.NODE_TIMEOUT)),
        retry_count=int(_coerce_int(slot.get("retryCount"), config.LLM_RETRY_COUNT)),
        fallback=_fallback_settings(slot.get("fallback")),
    )
    return settings, policy


def _settings_from_default(cfg: dict) -> tuple[ModelSettings, CallPolicy]:
    provider = cfg["provider"]
    model = cfg["model"]
    md = config.model_defaults(model)
    settings = ModelSettings(
        provider=provider,
        model=model,
        temperature=float(_coerce_float(cfg.get("temperature"), md.get("temperature"), 0.0)),
        max_tokens=md.get("max_tokens"),
        top_p=md.get("top_p"),
        stop=None,
        seed=None,
    )
    policy = CallPolicy(timeout_seconds=config.NODE_TIMEOUT, retry_count=config.LLM_RETRY_COUNT)
    return settings, policy


def _make_llm_step_node(
    node: dict,
    manifest: dict,
    model,
    policy: CallPolicy,
    emit: EventEmitter,
    run_id: str,
    loop_policy_ids: list[str] | None = None,
):
    node_id = node["id"]
    node_type = node["type"]
    spec = LLM_STEP_TABLE[node_type]
    system_prompt = (node.get("config") or {}).get("systemPrompt") or manifest.get(
        "defaults", {}
    ).get("systemPrompt", "")
    input_keys = [(p["id"], p["label"]) for p in manifest["inputs"]] + spec["extra_inputs"]
    policy_ids = loop_policy_ids or []

    async def step(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        usage: dict = {}
        result = await run_llm_step(
            state,
            node_id=node_id,
            system_prompt=system_prompt,
            input_keys=input_keys,
            output_model=spec["output_model"],
            model=model,
            emit=emit,
            run_id=run_id,
            call_policy=policy,
            usage_sink=usage,
        )
        updates = spec["to_updates"](result, state)
        if policy_ids and usage:
            updates["loop_runtime"] = {
                pid: {
                    "total_tokens": usage.get("prompt", 0) + usage.get("completion", 0),
                    "total_cost_usd": usage.get("cost", 0.0),
                }
                for pid in policy_ids
            }
        await emit(make_event(run_id, node_id, "node_end", output=spec["to_event_output"](result)))
        return updates

    return step


def _make_review_node(
    node: dict,
    model,
    policy: CallPolicy,
    emit: EventEmitter,
    run_id: str,
    loop_policy_ids: list[str] | None = None,
):
    node_cfg = node.get("config") or {}
    seed_criteria = [
        Criterion(id=f"cfg-{i + 1}", text=text).model_dump()
        for i, text in enumerate(node_cfg.get("criteria") or [])
        if isinstance(text, str) and text.strip()
    ]
    return make_review(
        model=model,
        emit=emit,
        run_id=run_id,
        node_id=node["id"],
        max_retries=int(node_cfg.get("maxRetries", config.MAX_RETRIES)),
        escalate_tags=set(node_cfg.get("escalateTags") or config.ESCALATE_TAGS),
        seed_criteria=seed_criteria,
        call_policy=policy,
        loop_policy_ids=loop_policy_ids,
    )


def _filter_control_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """io.input은 즉시 완료되는 가상 노드라 여러 target에 동시에 팬아웃할 수 있는데,
    그 중 하나가 실제 처리 노드(예: planning)를 거쳐 같은 target으로도 이어지면
    (예: input->reasoning 직결 + input->planning->reasoning) target이 두 번
    트리거된다 (LangGraph의 fan-in은 같은 슈퍼스텝에서 완료되는 병렬 브랜치만
    join하며, 슈퍼스텝이 어긋나면 각각 별도로 발화한다). task 등은 state에서
    항상 직접 읽으므로 직결 edge는 순서 제약으로서 불필요 — 제거한다.

    단, "같은 target에 다른 source가 있다"만으로 제거하면 안 된다: 그 다른
    source가 하류 피드백 루프(예: review->reasoning refine)라면 io.input발
    edge가 target을 깨우는 유일한 경로이기 때문이다. 그래서 직결 edge를 뺀
    그래프에서 io.input으로부터 target에 여전히 도달 가능할 때만 제거한다."""

    def _reachable(src: str, dst: str, skip: dict) -> bool:
        adjacency: dict[str, list[str]] = {}
        for e in edges:
            if e is skip:
                continue
            adjacency.setdefault(e["source"], []).append(e["target"])
        seen: set[str] = set()
        stack = [src]
        while stack:
            cur = stack.pop()
            if cur == dst:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adjacency.get(cur, []))
        return False

    nodes_by_id = {n["id"]: n for n in nodes}
    return [
        e
        for e in edges
        if not (
            nodes_by_id.get(e["source"], {}).get("type") == "io.input"
            and _reachable(e["source"], e["target"], skip=e)
        )
    ]


def _handle_targets(outgoing: dict[str, list[dict]], node_id: str) -> dict[str, str]:
    """노드의 outgoing 엣지를 sourceHandle → target 으로 인덱싱한다."""
    return {e["sourceHandle"]: e["target"] for e in outgoing.get(node_id, [])}


def _tarjan_scc(node_ids: list[str], edges: list[dict]) -> list[list[str]]:
    """Tarjan SCC. 크기 >= 2인 컴포넌트는 그 안에 최소 하나의 cycle이 있다는 뜻이다.

    ui/src/canvas/loops/loopCandidates.ts의 findStronglyConnectedComponents를
    포팅한 것 — Tier 판별용 countSimpleCyclesCapped는 UI 표시 목적이 사라져
    포팅하지 않는다(설계 §4).
    """
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for e in edges:
        if e["source"] in adjacency:
            adjacency[e["source"]].append(e["target"])

    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []

    def strong_connect(v: str) -> None:
        nonlocal index_counter
        indices[v] = index_counter
        lowlink[v] = index_counter
        index_counter += 1
        stack.append(v)
        on_stack.add(v)

        for w in adjacency.get(v, []):
            if w not in indices:
                strong_connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node_id in node_ids:
        if node_id not in indices:
            strong_connect(node_id)

    return components


def _validate_gated_cycles(node_ids: list[str], edges: list[dict], loop_node_ids: set[str]) -> None:
    """가드 없이 그려진 cycle은 컴파일 에러 — 무한 루프를 멈출 지점이 없다는 뜻이다.

    프론트 Loop Scope Lens가 담당하던 실수 방지 역할의 백엔드 이관(설계 §4).
    크기 1 컴포넌트(self-loop 포함)는 대상이 아니다.
    """
    for component in _tarjan_scc(node_ids, edges):
        if len(component) >= 2 and not (set(component) & loop_node_ids):
            raise ValueError(
                f"Cycle without a loop.guard node: {sorted(component)} — "
                "add a Loop node on the feedback edge"
            )


def _derive_loop_members(
    loop_node_id: str, continue_target: str | None, outgoing: dict[str, list[dict]]
) -> set[str]:
    """loopBack 타깃에서 출발해 다시 그 loop.guard 노드로 돌아오는 노드 집합 = 루프 본체.

    8/6 sidecar 설계의 사용자 선언 memberNodeIds를 그래프 도달 가능성으로 유도하는
    것으로 대체한다(설계 §3d). 토큰/비용 예산을 어떤 노드에 귀속시킬지 결정한다.
    """
    if continue_target is None:
        return set()

    # 전방: continue_target에서 도달 가능한 노드 (가드 자신은 경계이므로 넘지 않는다)
    forward: set[str] = set()
    stack = [continue_target]
    while stack:
        current = stack.pop()
        if current == loop_node_id or current in forward:
            continue
        forward.add(current)
        stack.extend(e["target"] for e in outgoing.get(current, []))

    # 후방: 가드로 되돌아올 수 있는 노드
    reverse: dict[str, list[str]] = {}
    for source, edge_list in outgoing.items():
        for e in edge_list:
            reverse.setdefault(e["target"], []).append(source)

    backward: set[str] = set()
    stack = [loop_node_id]
    while stack:
        current = stack.pop()
        if current in backward:
            continue
        backward.add(current)
        stack.extend(reverse.get(current, []))

    return forward & backward


_SCALAR_GUARD_KEYS = ("maxIterations", "maxTokens", "maxCostUsd", "maxDurationSec")


def _loop_policy_from_config(node: dict) -> dict:
    """loop.guard 노드의 평평한 config를 evaluate_loop_guard가 기대하는 중첩 dict로 재조립.

    이 어댑터가 있어서 nodes/loop_guard.py(순수 가드 평가 코어)는 캔버스 노드
    계약을 전혀 모른 채 그대로 재사용된다. stuckThreshold가 비어 있으면 키 자체를
    넣지 않는다 — None을 넣으면 _is_stuck의 float(None)이 TypeError가 된다.
    """
    cfg = node.get("config") or {}
    guard: dict = {key: cfg[key] for key in _SCALAR_GUARD_KEYS if cfg.get(key) is not None}
    if cfg.get("stuckWindow") is not None:
        stuck: dict = {"window": cfg["stuckWindow"]}
        if cfg.get("stuckThreshold") is not None:
            stuck["threshold"] = cfg["stuckThreshold"]
        guard["stuck"] = stuck
    return {"id": node["id"], "onExhaustion": cfg.get("onExhaustion", "exit"), "guard": guard}


def _make_loop_guard_node(
    policy: dict,
    guard_node_id: str,
    continue_target: str,
    exit_target: str | None,
    emit: EventEmitter,
    run_id: str,
):
    policy_id = policy["id"]
    on_exhaustion = policy["onExhaustion"]
    max_iterations = (policy.get("guard") or {}).get("maxIterations")

    async def loop_guard(state: AgentState) -> Command:
        await emit(make_event(run_id, guard_node_id, "node_start"))

        prior = (state.get("loop_runtime") or {}).get(policy_id)
        runtime = next_runtime(prior)
        result = evaluate_loop_guard(policy, runtime)
        update = {"iteration": runtime["iteration"], "started_at": runtime["started_at"]}

        loop_runtime_event: dict = {
            "loopNodeId": policy_id,
            "iteration": runtime["iteration"],
            "tokens": runtime["total_tokens"],
            "costUsd": runtime["total_cost_usd"],
            "durationMs": int((time.time() - runtime["started_at"]) * 1000),
        }
        if max_iterations is not None:
            loop_runtime_event["maxIterations"] = max_iterations
        if runtime["last_feedback"] is not None:
            loop_runtime_event["lastFeedback"] = runtime["last_feedback"]
        if not result["should_continue"]:
            loop_runtime_event["exitReason"] = result["exit_reason"]
        await emit(make_event(run_id, guard_node_id, "node_end", loop_runtime=loop_runtime_event))

        if result["should_continue"]:
            return Command(goto=continue_target, update={"loop_runtime": {policy_id: update}})

        if on_exhaustion == "fail":
            raise RuntimeError(
                f"loop.guard node {policy_id!r} exhausted ({result['exit_reason']}) "
                "with onExhaustion='fail'"
            )
        return Command(goto=exit_target, update={"loop_runtime": {policy_id: update}})

    return loop_guard


def compile_graph(architecture: dict, default_model_cfg: dict, emit: EventEmitter, run_id: str):
    nodes: list[dict] = architecture.get("nodes") or []
    raw_edges: list[dict] = architecture.get("edges") or []

    if not nodes:
        raise ValueError("Architecture has no nodes")

    edges = _filter_control_edges(nodes, raw_edges)

    outgoing: dict[str, list[dict]] = {}
    incoming: dict[str, list[dict]] = {}
    for e in edges:
        outgoing.setdefault(e["source"], []).append(e)
        incoming.setdefault(e["target"], []).append(e)

    loop_node_ids = {n["id"] for n in nodes if n["type"] == "loop.guard"}
    _validate_gated_cycles([n["id"] for n in nodes], edges, loop_node_ids)

    # 토큰/비용 예산을 귀속시킬 루프 본체를 그래프에서 유도한다 (설계 §3d).
    # 파라미터 이름 loop_policy_ids는 review/llm_step 쪽 무변경을 위해 유지된다.
    node_to_policies: dict[str, list[str]] = {}
    for loop_node_id in sorted(loop_node_ids):
        continue_target = _handle_targets(outgoing, loop_node_id).get("loopBack")
        for member_id in sorted(_derive_loop_members(loop_node_id, continue_target, outgoing)):
            node_to_policies.setdefault(member_id, []).append(loop_node_id)

    graph = StateGraph(AgentState)
    route_fns: dict[str, Any] = {}

    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        manifest = MANIFESTS_BY_TYPE.get(node_type)
        if manifest is None:
            raise ValueError(f"Unknown node type: {node_type!r} (node {node_id!r})")

        if node_type in PASSTHROUGH_TYPES:
            graph.add_node(
                node_id,
                _make_passthrough_node(node_id, node_type, node.get("config") or {}, emit, run_id),
            )
        elif manifest.get("runtime") == "llm_step":
            model, policy = _resolve_model(node, default_model_cfg)
            graph.add_node(
                node_id,
                _make_llm_step_node(
                    node, manifest, model, policy, emit, run_id, node_to_policies.get(node_id)
                ),
            )
        elif node_type == "review.intent":
            model, policy = _resolve_model(node, default_model_cfg)
            wired = {e["sourceHandle"] for e in outgoing.get(node_id, [])}
            route_fns[node_id] = make_route_review(wired)
            graph.add_node(
                node_id,
                _make_review_node(node, model, policy, emit, run_id, node_to_policies.get(node_id)),
            )
        elif node_type == "human.checkpoint":
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update(_handle_targets(outgoing, node_id))
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
        elif node_type == "loop.guard":
            loop_policy = _loop_policy_from_config(node)
            targets = _handle_targets(outgoing, node_id)
            continue_target = targets.get("loopBack")
            exit_target = targets.get("exit")
            on_exhaustion = loop_policy["onExhaustion"]

            if continue_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} has no 'loopBack' edge — "
                    "wire the Loop back port to the node the loop re-enters"
                )
            if on_exhaustion not in ("exit", "escalate", "fail"):
                raise ValueError(
                    f"loop.guard node {node_id!r} has invalid onExhaustion "
                    f"{on_exhaustion!r} (must be 'exit', 'escalate', or 'fail')"
                )
            if on_exhaustion in ("exit", "escalate") and exit_target is None:
                raise ValueError(
                    f"loop.guard node {node_id!r} onExhaustion={on_exhaustion!r} "
                    "requires a wired 'exit' port"
                )

            graph.add_node(
                node_id,
                _make_loop_guard_node(
                    loop_policy,
                    node_id,
                    continue_target=continue_target,
                    exit_target=exit_target,
                    emit=emit,
                    run_id=run_id,
                ),
            )
        else:
            raise ValueError(f"Unsupported node type in compiler: {node_type!r}")

    added_plain_edges: set[tuple[str, str]] = set()
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        outs = outgoing.get(node_id, [])

        if node_type == "review.intent":
            graph.add_conditional_edges(
                node_id, route_fns[node_id], _handle_targets(outgoing, node_id)
            )
            continue
        # human.checkpoint / loop.guard는 Command(goto=...)로 스스로 라우팅하므로
        # plain edge를 추가하지 않는다.
        if node_type in ("human.checkpoint", "loop.guard"):
            continue

        if not outs:
            graph.add_edge(node_id, END)
            continue
        for e in outs:
            pair = (node_id, e["target"])
            if pair in added_plain_edges:
                continue
            added_plain_edges.add(pair)
            graph.add_edge(node_id, e["target"])

    entry_ids = [n["id"] for n in nodes if not incoming.get(n["id"])]
    if not entry_ids:
        raise ValueError("Architecture has no entry node (a node with no incoming edges)")
    for eid in entry_ids:
        graph.add_edge(START, eid)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
