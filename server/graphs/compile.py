"""
compile_graph: 캔버스에서 직렬화된 Architecture(dict)를 실행 가능한 LangGraph
StateGraph로 컴파일한다. v0.1의 고정 그래프(baseline.py/treatment.py) 디스패치를
대체하는 v0.3 seam — dispatch_graph가 'gsm8k-baseline'/'gsm8k-treatment' 외의
아키텍처 이름을 여기로 폴백한다.
"""
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

import config
from events import EventEmitter, make_event
from manifests import BUILTIN_MANIFESTS
from models import PlanOut, ReasonOut, VerdictOut, build_model
from nodes.checkpoint import make_human_checkpoint
from nodes.llm_step import run_llm_step
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
    "verification.auto": {
        "output_model": VerdictOut,
        "extra_inputs": [],
        "to_updates": lambda result, state: {
            "verdict": {"passed": result["passed"], "feedback": result["feedback"]},
            "feedback": result["feedback"],
            "retries": (state.get("retries") or 0) + 1,
        },
        "to_event_output": lambda result: {
            "passed": result["passed"],
            "feedback": result["feedback"],
        },
    },
}

PASSTHROUGH_TYPES = {"io.input", "io.output", "model.binding"}


def _make_passthrough_node(node_id: str, node_type: str, emit: EventEmitter, run_id: str):
    async def passthrough(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        output = None
        if node_type == "io.output":
            output = {"answer": state.get("answer"), "verdict": state.get("verdict")}
        await emit(make_event(run_id, node_id, "node_end", output=output))
        return {}

    return passthrough


def _resolve_model(node: dict, default_model_cfg: dict):
    slots = (node.get("config") or {}).get("modelSlots") or []
    if slots:
        slot = slots[0]
        return build_model(slot["provider"], slot["model"], float(slot.get("temperature", 0)))
    return build_model(
        default_model_cfg["provider"],
        default_model_cfg["model"],
        float(default_model_cfg["temperature"]),
    )


def _make_llm_step_node(node: dict, manifest: dict, model, emit: EventEmitter, run_id: str):
    node_id = node["id"]
    node_type = node["type"]
    spec = LLM_STEP_TABLE[node_type]
    system_prompt = (node.get("config") or {}).get("systemPrompt") or manifest.get(
        "defaults", {}
    ).get("systemPrompt", "")
    input_keys = [(p["id"], p["label"]) for p in manifest["inputs"]] + spec["extra_inputs"]

    async def step(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        result = await run_llm_step(
            state,
            node_id=node_id,
            system_prompt=system_prompt,
            input_keys=input_keys,
            output_model=spec["output_model"],
            model=model,
            emit=emit,
            run_id=run_id,
        )
        updates = spec["to_updates"](result, state)
        await emit(make_event(run_id, node_id, "node_end", output=spec["to_event_output"](result)))
        return updates

    return step


def _make_branch_computer(node_cfg: dict):
    pass_threshold = float(node_cfg.get("passThreshold", config.PASS_THRESHOLD))
    auto_threshold = float(node_cfg.get("autoThreshold", config.AUTO_THRESHOLD))
    escalate_tags = set(node_cfg.get("escalateTags") or config.ESCALATE_TAGS)

    def compute(state: AgentState) -> str:
        c = state.get("confidence") or 0.0
        tags = set(state.get("task_tags") or [])
        if tags & escalate_tags:
            branch = "human"
        elif c >= pass_threshold:
            branch = "pass"
        elif c >= auto_threshold:
            branch = "auto"
        else:
            branch = "human"
        if branch == "human" and state.get("batch_mode"):
            branch = "auto"
        return branch

    return compute


def _make_policy_node(node_id: str, compute_branch, emit: EventEmitter, run_id: str):
    async def policy(state: AgentState) -> dict:
        await emit(make_event(run_id, node_id, "node_start"))
        branch = compute_branch(state)
        c = state.get("confidence") or 0.0
        await emit(make_event(
            run_id, node_id, "node_end",
            policy_decision={"activated": branch != "pass", "reason": f"conf {c:.2f} -> {branch}"},
        ))
        return {}

    return policy


def _make_route_review(node_id: str, compute_branch, wired: set[str]):
    def route(state: AgentState) -> str:
        branch = compute_branch(state)
        if branch in wired:
            return branch
        for fallback in ("pass", "auto", "human"):
            if fallback in wired:
                return fallback
        raise ValueError(f"policy.review node {node_id!r} has no outgoing edges")

    return route


def _filter_control_edges(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """io.input은 즉시 완료되는 가상 노드라 여러 target에 동시에 팬아웃할 수 있는데,
    그 중 하나가 실제 처리 노드(예: planning)를 거쳐 같은 target으로도 이어지면
    (예: input->reasoning 직결 + input->planning->reasoning) target이 두 번
    트리거된다 (LangGraph의 fan-in은 같은 슈퍼스텝에서 완료되는 병렬 브랜치만
    join하며, 슈퍼스텝이 어긋나면 각각 별도로 발화한다). task 등은 state에서
    항상 직접 읽으므로 실제 선행 처리 노드가 이미 있는 target에 한해
    io.input발 edge는 순서 제약으로서 불필요 — 제거한다."""
    nodes_by_id = {n["id"]: n for n in nodes}
    targets_with_real_source = {
        e["target"] for e in edges if nodes_by_id.get(e["source"], {}).get("type") != "io.input"
    }
    return [
        e for e in edges
        if not (
            nodes_by_id.get(e["source"], {}).get("type") == "io.input"
            and e["target"] in targets_with_real_source
        )
    ]


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

    graph = StateGraph(AgentState)
    route_fns: dict[str, Any] = {}

    for node in nodes:
        node_id = node["id"]
        node_type = node["type"]
        manifest = MANIFESTS_BY_TYPE.get(node_type)
        if manifest is None:
            raise ValueError(f"Unknown node type: {node_type!r} (node {node_id!r})")

        if node_type in PASSTHROUGH_TYPES:
            graph.add_node(node_id, _make_passthrough_node(node_id, node_type, emit, run_id))
        elif manifest.get("runtime") == "llm_step":
            model = _resolve_model(node, default_model_cfg)
            graph.add_node(node_id, _make_llm_step_node(node, manifest, model, emit, run_id))
        elif node_type == "policy.review":
            compute_branch = _make_branch_computer(node.get("config") or {})
            wired = {e["sourceHandle"] for e in outgoing.get(node_id, [])}
            route_fns[node_id] = _make_route_review(node_id, compute_branch, wired)
            graph.add_node(node_id, _make_policy_node(node_id, compute_branch, emit, run_id))
        elif node_type == "human.checkpoint":
            routes = {"approve": END, "revise": END, "reject": END}
            routes.update({e["sourceHandle"]: e["target"] for e in outgoing.get(node_id, [])})
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

        if node_type == "policy.review":
            mapping = {e["sourceHandle"]: e["target"] for e in outs}
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
