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
from events import EventEmitter
from graphs.compile import compile_graph
from logging_config import logger
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
) -> RunOutcome:
    workspace.write_run_record(
        run_id,
        {
            "runId": run_id,
            "archPath": arch_path,
            "archText": arch_text,
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
    workspace.update_run_record(run_id, status="running", error=None)
    return await _invoke(
        rec["architecture"], rec["modelCfg"], run_id, Command(resume=decision), emit, checkpointer
    )
