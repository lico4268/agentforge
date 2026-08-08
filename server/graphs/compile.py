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


def _prepare_loop_policies(
    loop_policies: list[dict], nodes_by_id: dict[str, dict], edges_by_id: dict[str, dict]
) -> tuple[dict[str, str], list[dict], dict[str, list[str]]]:
    """LoopPolicy 목록을 검증하고, 컴파일러가 쓸 세 가지 파생 구조를 만든다.

    - edge_target_override: feedbackEdgeId → guard 노드 id (조건부 라우팅 재작성용)
    - guard_specs: 각 정책의 guard 노드 등록에 필요한 정보
    - node_to_policies: memberNodeId → 소속 정책 id 목록 (토큰/비용 귀속용, Task 6)
    """
    edge_target_override: dict[str, str] = {}
    guard_specs: list[dict] = []
    node_to_policies: dict[str, list[str]] = {}

    for policy in loop_policies:
        policy_id = policy.get("id")
        if not policy_id:
            raise ValueError("LoopPolicy is missing required field 'id'")

        on_exhaustion = policy.get("onExhaustion")
        if on_exhaustion not in ("exit", "escalate", "fail"):
            raise ValueError(
                f"LoopPolicy {policy_id!r} has invalid onExhaustion {on_exhaustion!r} "
                "(must be 'exit', 'escalate', or 'fail')"
            )

        guard_node_id = f"__loop_guard__{policy_id}"

        feedback_edges = []
        for edge_id in policy.get("feedbackEdgeIds") or []:
            edge = edges_by_id.get(edge_id)
            if edge is None:
                raise ValueError(
                    f"LoopPolicy {policy_id!r} references unknown feedbackEdgeId {edge_id!r}"
                )
            source_type = nodes_by_id.get(edge["source"], {}).get("type")
            if source_type not in ("review.intent", "human.checkpoint"):
                raise ValueError(
                    f"LoopPolicy {policy_id!r} feedback edge {edge_id!r} has source type "
                    f"{source_type!r}, which does not support loop guards "
                    "(v1 supports review.intent/human.checkpoint only)"
                )
            feedback_edges.append(edge)

        targets = {e["target"] for e in feedback_edges}
        if len(targets) != 1:
            raise ValueError(
                f"LoopPolicy {policy_id!r} feedbackEdgeIds must share a single re-entry "
                f"target, got {sorted(targets)!r}"
            )
        continue_target = targets.pop()

        exit_target: str | None = None
        exit_edge_ids = policy.get("exitEdgeIds") or []
        if exit_edge_ids:
            exit_edge_id = exit_edge_ids[0]
            exit_edge = edges_by_id.get(exit_edge_id)
            if exit_edge is None:
                raise ValueError(
                    f"LoopPolicy {policy_id!r} references unknown exitEdgeId {exit_edge_id!r}"
                )
            exit_target = exit_edge["target"]
        if on_exhaustion in ("exit", "escalate") and exit_target is None:
            raise ValueError(
                f"LoopPolicy {policy_id!r} onExhaustion={on_exhaustion!r} "
                "requires a non-empty exitEdgeIds"
            )

        for edge in feedback_edges:
            edge_target_override[edge["id"]] = guard_node_id

        for member_id in policy.get("memberNodeIds") or []:
            node_to_policies.setdefault(member_id, []).append(policy_id)

        guard_specs.append(
            {
                "policy": policy,
                "guard_node_id": guard_node_id,
                "continue_target": continue_target,
                "exit_target": exit_target,
            }
        )

    return edge_target_override, guard_specs, node_to_policies


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
                f"LoopPolicy {policy_id!r} exhausted ({result['exit_reason']}) "
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

    nodes_by_id = {n["id"]: n for n in nodes}
    edges_by_id = {e["id"]: e for e in edges}
    loop_policies: list[dict] = architecture.get("loopPolicies") or []
    edge_target_override, guard_specs, node_to_policies = _prepare_loop_policies(
        loop_policies, nodes_by_id, edges_by_id
    )

    graph = StateGraph(AgentState)
    route_fns: dict[str, Any] = {}

    for spec in guard_specs:
        graph.add_node(
            spec["guard_node_id"],
            _make_loop_guard_node(
                spec["policy"],
                spec["guard_node_id"],
                spec["continue_target"],
                spec["exit_target"],
                emit,
                run_id,
            ),
        )

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
            routes.update(
                {
                    e["sourceHandle"]: edge_target_override.get(e["id"], e["target"])
                    for e in outgoing.get(node_id, [])
                }
            )
            graph.add_node(
                node_id,
                make_human_checkpoint(emit, run_id, routes=routes, node_id=node_id),
            )
        else:
            raise ValueError(f"Unsupported node type in compiler: {node_type!r}")

    added_plain_edges: set[tuple[str, str]] = set()
    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        outs = outgoing.get(node_id, [])

        if node_type == "review.intent":
            mapping = {
                e["sourceHandle"]: edge_target_override.get(e["id"], e["target"]) for e in outs
            }
            graph.add_conditional_edges(node_id, route_fns[node_id], mapping)
            continue
        if node_type == "human.checkpoint":
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
