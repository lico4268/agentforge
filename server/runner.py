"""Shared start/resume core for the CLI and the WebSocket server."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

import config as cfg
import workspace
from events import EventEmitter, ListEventEmitter
from graphs.compile import PASSTHROUGH_TYPES, compile_graph
from logging_config import logger
from replay import ReplayError, pick_from, reuse_stats, visit_order
from state import initial_state

DEFAULT_MODEL_CFG = {
    "provider": "google",
    "model": "gemini-3.1-flash-lite",
    "temperature": 0.0,
}
RECURSION_LIMIT = cfg.MAX_RETRIES * 10 + 20


def checkpoint_db() -> Path:
    return workspace.WORKSPACE_DIR / "checkpoints.sqlite"


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    db = checkpoint_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(db)) as cp:
        yield cp


@dataclass
class RunOutcome:
    run_id: str
    status: Literal["done", "paused", "error"]
    final: dict | None
    error: str | None


async def _invoke(
    architecture: dict, model_cfg: dict, run_id: str, inp, emit: EventEmitter, checkpointer
) -> RunOutcome:
    try:
        graph = compile_graph(
            architecture, {**DEFAULT_MODEL_CFG, **model_cfg}, emit, run_id, checkpointer
        )
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": RECURSION_LIMIT}
        final = await graph.ainvoke(inp, config=config)
        status = "paused" if final.get("__interrupt__") else "done"
        outcome = RunOutcome(run_id, status, final, None)
    except Exception as e:
        logger.exception("run %s failed", run_id)
        outcome = RunOutcome(run_id, "error", None, f"{type(e).__name__}: {e}")
    workspace.update_run_record(run_id, status=outcome.status, error=outcome.error)
    return outcome


async def start_run(
    architecture: dict,
    *,
    run_id: str,
    task: str,
    model_cfg: dict,
    emit: EventEmitter,
    checkpointer,
    arch_path: str | None = None,
    arch_text: str | None = None,
    default_model: str | None = None,
) -> RunOutcome:
    workspace.write_run_record(
        run_id,
        {
            "runId": run_id,
            "archPath": arch_path,
            "archText": arch_text,
            "defaultModel": default_model,
            "architecture": architecture,
            "modelCfg": model_cfg,
            "task": task,
            "createdAt": datetime.now(UTC).isoformat(),
            "status": "running",
            "error": None,
        },
    )
    return await _invoke(
        architecture, model_cfg, run_id, initial_state(task=task), emit, checkpointer
    )


async def resume_run(
    run_id: str, decision: dict, *, emit: EventEmitter, checkpointer
) -> RunOutcome:
    rec = workspace.read_run_record(run_id)
    if rec is None:
        raise LookupError(f"unknown run: {run_id}")
    if checkpointer is not None and not await checkpointer.aget_tuple(
        {"configurable": {"thread_id": run_id}}
    ):
        err = f"no checkpoint for run {run_id}"
        workspace.update_run_record(run_id, status="error", error=err)
        return RunOutcome(run_id, "error", None, err)
    workspace.update_run_record(run_id, status="running", error=None)
    return await _invoke(
        rec["architecture"], rec["modelCfg"], run_id, Command(resume=decision), emit, checkpointer
    )


async def replay_run(
    parent_id: str,
    architecture: dict,
    *,
    run_id: str,
    from_node: str | None,
    emit: EventEmitter,
    checkpointer,
    arch_path: str | None = None,
    arch_text: str | None = None,
    default_model: str | None = None,
) -> RunOutcome:
    """Fork the parent's checkpoint taken just before the start node into a new run and continue."""
    rec = workspace.read_run_record(parent_id)
    if rec is None:
        raise LookupError(f"unknown run: {parent_id}")
    reused = rec.get("reused", [])
    evs = workspace.read_events(parent_id)
    start = pick_from(rec["architecture"], architecture, visit_order(evs, reused), from_node)
    if start in reused:
        raise ReplayError(
            f"node '{start}' was reused from run {rec['parent']['runId']} — replay that run instead"
        )
    old = rec["architecture"]
    graph = compile_graph(
        old,
        {**DEFAULT_MODEL_CFG, **rec["modelCfg"]},
        ListEventEmitter(),
        parent_id,
        checkpointer,
    )
    history = [
        s async for s in graph.aget_state_history({"configurable": {"thread_id": parent_id}})
    ]
    # newest first, so the last match is the oldest snapshot: just before first visit
    snaps = [s for s in history if start in s.next]
    if not snaps:
        raise ReplayError(f"no checkpoint before '{start}' in run {parent_id}")
    snap = snaps[-1]
    tup = await checkpointer.aget_tuple(snap.config)
    await checkpointer.aput(
        {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}},
        tup.checkpoint,
        tup.metadata,
        tup.checkpoint["channel_versions"],
    )
    hidden = {n["id"] for n in old["nodes"] if n["type"] in PASSTHROUGH_TYPES}
    nodes, cost = reuse_stats(evs, start, snap.next, hidden)
    workspace.write_run_record(
        run_id,
        {
            "runId": run_id,
            "archPath": arch_path,
            "archText": arch_text,
            "defaultModel": default_model,
            "architecture": architecture,
            "modelCfg": rec["modelCfg"],
            "task": rec["task"],
            "createdAt": datetime.now(UTC).isoformat(),
            "status": "running",
            "error": None,
            "parent": {
                "runId": parent_id,
                "checkpointId": snap.config["configurable"]["checkpoint_id"],
            },
            "fromNode": start,
            "reused": [*reused, *nodes],
            "savedCost": None
            if cost is None or rec.get("savedCost", 0) is None
            else rec.get("savedCost", 0) + cost,
        },
    )
    return await _invoke(architecture, rec["modelCfg"], run_id, None, emit, checkpointer)


def usd(cost: float | None) -> str:
    return "$?" if cost is None else f"${cost:.6f}"


def _body(output) -> str | None:
    body = workspace._extract_body(output)
    if body is None and isinstance(output, dict):
        body = next((v for v in output.values() if isinstance(v, str)), None)
    return body


def summarize(events: list[dict], hidden: set[str]) -> dict:
    visits: list[dict] = []
    current: dict[str, dict] = {}  # node id -> its open visit
    interrupt = None
    result = None

    def visit(node: str) -> dict:
        if node not in current:
            v = {
                "node": node,
                "status": "running",
                "tokens": 0,
                "cost": 0.0,
                "model": None,
                "preview": "",
                "route": None,
            }
            current[node] = v
            visits.append(v)
        return current[node]

    for ev in events:
        t, node, out = ev.get("eventType"), ev.get("nodeId"), ev.get("output")
        if t == "node_start":
            current.pop(node, None)
            visit(node)
        elif t == "log" and ev.get("tokenUsage"):
            u, v = ev["tokenUsage"], visit(node)
            v["tokens"] += u.get("total_tokens", 0)
            c = u.get("cost")
            v["cost"] = None if c is None or v["cost"] is None else v["cost"] + c
            v["model"] = u.get("model") or v["model"]
        elif t == "node_end":
            v = visit(node)
            v["status"] = "done"
            v["preview"] = _body(out) or ""
            if isinstance(out, dict):
                v["route"] = next((x for k, x in out.items() if k.startswith("__route__")), None)
            if node not in hidden:
                result = _body(out)
        elif t == "error":
            v = visit(node)
            v["status"], v["preview"] = "failed", ev.get("message") or ""
        elif t == "interrupt":
            visit(node)["status"] = "paused"
            interrupt = {"node": node, "question": out["summary"], "choices": out["actions"]}
        elif t == "decision_record":
            v = visit(node)
            v["status"], v["route"] = "done", out["decision"]
    visits = [v for v in visits if v["node"] not in hidden]
    if interrupt and interrupt["node"] in hidden:
        interrupt = None
    # an interrupt that was later resolved is no longer pending
    if interrupt and current.get(interrupt["node"], {}).get("status") != "paused":
        interrupt = None
    costs = [v["cost"] for v in visits]
    return {
        "visits": visits,
        "totalTokens": sum(v["tokens"] for v in visits),
        "totalCost": None if None in costs else sum(costs),
        "unpricedModels": sorted({v["model"] or "?" for v in visits if v["cost"] is None}),
        "interrupt": interrupt,
        "result": result,
    }
