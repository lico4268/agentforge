import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import arch_files
import config as cfg
import openrouter_catalog as orc
import workspace
from archfile import ArchError
from events import WSEventEmitter, safe_send_json
from logging_config import logger, setup_logging
from runner import open_checkpointer, resume_run, start_run

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One SQLite checkpointer shared with the CLI, so paused runs survive a server restart.
    async with open_checkpointer() as cp:
        app.state.checkpointer = cp
        try:
            yield
        finally:
            app.state.checkpointer = None  # the connection closes with this block


app = FastAPI(title="Agentforge Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Model list ───────────────────────────────────────────────────────────────────


def _load_models_config() -> list[dict]:
    """From config.yaml models.list, return only enabled models + dynamically add OpenRouter
    favorites.
    Providers with no API key set are marked available=False.

    OpenRouter is not listed statically in config.yaml — it has hundreds of models, so
    only those picked via openrouter_catalog.load_favorites() are exposed."""
    key_by_provider = {
        "anthropic": bool(cfg.ANTHROPIC_API_KEY),
        "openai": bool(cfg.OPENAI_API_KEY),
        "google": bool(cfg.GOOGLE_API_KEY),
        "local": True,
        "openrouter": bool(cfg.OPENROUTER_API_KEY),
    }

    result = []
    for m in cfg.MODELS_LIST:
        if not m.get("enabled", True):
            continue
        provider = m.get("provider", "")
        result.append(
            {
                "id": m["id"],
                "provider": provider,
                "label": m.get("label", m["id"]),
                "description": m.get("description", ""),
                "available": key_by_provider.get(provider, False),
                "temperature": m.get("temperature", 0.7),
                "maxTokens": m.get("max_tokens", 4096),
            }
        )

    for model_id in orc.load_favorites():
        result.append(
            {
                "id": model_id,
                "provider": "openrouter",
                "label": orc.cached_label(model_id),
                "description": "",
                "available": key_by_provider["openrouter"],
                "temperature": 0.7,
                "maxTokens": 8192,
            }
        )
    return result


# ─── REST endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/models")
async def get_models() -> list[dict]:
    """Model list based on models_config.json. The available field shows whether an API key is
    set."""
    return _load_models_config()


@app.get("/api/arch")
async def list_arch() -> list[dict]:
    """List of server/arch/*.yaml — arch.yaml files hand-authored in an editor."""
    return arch_files.list_arch_files()


@app.get("/api/arch/{name}")
async def get_arch(name: str) -> dict:
    try:
        return arch_files.read_arch_file(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"arch file not found: {name}") from None
    except (ArchError, ValueError) as err:
        raise HTTPException(status_code=400, detail=str(err)) from None


# ─── OpenRouter favorites ─────────────────────────────────────────────────────────


@app.get("/api/openrouter/catalog")
async def get_openrouter_catalog() -> list[dict]:
    """For the favorites picker screen — the full OpenRouter catalog (live, cached)."""
    try:
        return await orc.get_catalog()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter catalog fetch failed: {e}") from e


@app.get("/api/openrouter/favorites")
async def get_openrouter_favorites() -> list[str]:
    return orc.load_favorites()


@app.put("/api/openrouter/favorites")
async def put_openrouter_favorites(ids: list[str]) -> list[str]:
    """Update the list of OpenRouter model ids exposed in the node UI/Inspector model slots."""
    return orc.save_favorites(ids)


# ─── Workspace files (run output persistence) ───────────────────────────────────────


@app.get("/api/runs/{run_id}/files")
async def list_run_files(run_id: str) -> list[dict]:
    """List of node output files for the run_id directory (camelCase)."""
    from workspace import list_run_files as _list

    return _list(run_id)


@app.get("/api/runs/{run_id}/files/{name}")
async def read_run_file(run_id: str, name: str) -> dict:
    """Contents of a single workspace file."""
    from workspace import read_run_file as _read

    result = _read(run_id, name)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result


async def _send_run_outcome(ws, run_id: str, final: dict, history: list) -> None:
    """Distinguish whether the graph.ainvoke() result is a pause caused by an interrupt or a normal
    completion, and send accordingly.

    LangGraph, when interrupt() is called, returns the final state with an "__interrupt__" key
    filled in, without raising — if this is not checked, a pause is mistaken for completion
    run_complete(answer=null) is sent, and the frontend shows the run as finished even though the
    graph is actually waiting.
    """
    if final.get("__interrupt__"):
        last_interrupt = next(
            (e for e in reversed(history) if e.event_type == "interrupt"),
            None,
        )
        await safe_send_json(
            ws,
            {
                "kind": "interrupt",
                "runId": run_id,
                "nodeId": last_interrupt.node_id if last_interrupt else "",
                "payload": last_interrupt.output if last_interrupt else {},
            },
        )
        return

    await safe_send_json(
        ws,
        {
            "kind": "run_complete",
            "runId": run_id,
            "result": {
                "answer": final.get("answer"),
                "reviewDelta": final.get("review_delta"),
                "reviewBranch": final.get("review_branch"),
            },
        },
    )


# ─── WebSocket run handler ────────────────────────────────────────────────────────

# Max number of runs to keep in run_history — beyond that evict the oldest first (prevents
# unbounded growth)
MAX_RUN_HISTORY = 50

# run_id → accumulated events (to resend on reconnect)
run_history: dict[str, list] = {}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()
    current_run_id: str | None = None

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("kind")

            if kind == "run":
                run_id = str(uuid.uuid4())
                current_run_id = run_id
                history: list = []
                run_history[run_id] = history
                while len(run_history) > MAX_RUN_HISTORY:
                    del run_history[next(iter(run_history))]
                await safe_send_json(ws, {"kind": "run_started", "runId": run_id})

                arch_file = msg.get("archFile") or ""
                try:
                    arch = arch_files.read_arch_file(arch_file)["architecture"]
                except FileNotFoundError:
                    message = f"arch file not found: {arch_file}"
                except ValueError as e:  # ArchError (with line number) or a bad file name
                    message = str(e)
                else:
                    outcome = await start_run(
                        arch,
                        run_id=run_id,
                        task=(msg.get("input") or {}).get("task", ""),
                        model_cfg=msg.get("model") or {},
                        emit=WSEventEmitter(ws, run_id, history),
                        checkpointer=getattr(app.state, "checkpointer", None),
                        arch_path=arch_file,
                    )
                    if not outcome.error:
                        await _send_run_outcome(ws, run_id, outcome.final, history)
                        continue
                    message = outcome.error
                logger.warning("run %s failed: %s", run_id, message)
                await safe_send_json(ws, {"kind": "error", "runId": run_id, "message": message})

            elif kind == "resume":
                run_id = msg.get("runId") or current_run_id
                rec = workspace.read_run_record(run_id) if run_id else None
                if rec is None:
                    message = "Run not found"
                elif rec.get("status") != "paused":
                    message = f"Run {run_id} is not paused (status: {rec.get('status')})"
                else:
                    history = run_history.setdefault(run_id, [])
                    outcome = await resume_run(
                        run_id,
                        msg.get("decision") or {},
                        emit=WSEventEmitter(ws, run_id, history),
                        checkpointer=getattr(app.state, "checkpointer", None),
                    )
                    if not outcome.error:
                        await _send_run_outcome(ws, run_id, outcome.final, history)
                        continue
                    message = outcome.error
                await safe_send_json(ws, {"kind": "error", "runId": run_id, "message": message})

            elif kind == "reconnect":
                run_id = msg.get("runId", "")
                history = run_history.get(run_id, [])
                snapshot = [ev.to_frontend() for ev in history]
                await safe_send_json(ws, {"kind": "state", "runId": run_id, "snapshot": snapshot})

    except WebSocketDisconnect:
        pass
