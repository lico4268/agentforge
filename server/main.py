import json
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import arch_files
import config as cfg
import openrouter_catalog as orc
from archfile import ArchError
from events import WSEventEmitter, safe_send_json
from logging_config import logger, setup_logging
from manifests import BUILTIN_MANIFESTS
from models import ModelSettings, build_model
from runner import DEFAULT_MODEL_CFG, RECURSION_LIMIT
from state import initial_state

setup_logging()
app = FastAPI(title="Agentforge Backend", version="0.1.0")

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


# ─── Architecture file store (v0.1, file-based) ─────────────────────────────────────

ARCHITECTURE_JSON_DIR = Path(__file__).parent / "architectures"
ARCHITECTURE_JSON_DIR.mkdir(exist_ok=True)

# ─── REST endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/models")
async def get_models() -> list[dict]:
    """Model list based on models_config.json. The available field shows whether an API key is
    set."""
    return _load_models_config()


@app.get("/api/nodes")
async def get_nodes() -> list[dict]:
    return BUILTIN_MANIFESTS


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


@app.get("/api/architectures")
async def list_architectures() -> list[dict]:
    result = []
    for f in ARCHITECTURE_JSON_DIR.glob("*.json"):
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return result


@app.post("/api/architectures")
async def save_architecture(body: dict) -> dict:
    arch_id = body.get("id") or str(uuid.uuid4())
    body["id"] = arch_id
    path = ARCHITECTURE_JSON_DIR / f"{arch_id}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2))
    return body


@app.get("/api/architectures/{arch_id}")
async def get_architecture(arch_id: str) -> dict:
    path = ARCHITECTURE_JSON_DIR / f"{arch_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Architecture not found")
    return json.loads(path.read_text())


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


# ─── Graph dispatcher ─────────────────────────────────────────────────────────────


def _model_settings(c: dict) -> ModelSettings:
    """Toolbar model selection → ModelSettings. Inherits max_tokens/top_p from the model defaults
    (config.yaml)."""
    md = cfg.model_defaults(c["model"])
    return ModelSettings(
        provider=c["provider"],
        model=c["model"],
        temperature=float(c.get("temperature", 0.0) or 0.0),
        max_tokens=md.get("max_tokens"),
        top_p=md.get("top_p"),
    )


def dispatch_graph(architecture: dict, model_cfg: dict, emit: Any, run_id: str):
    """
    v0.1: the names 'gsm8k-baseline'/'gsm8k-treatment' dispatch to the fixed graph builders.
    v0.3: anything else compiles the canvas directly with compile_graph(architecture) (§8 seam).

    Fixed-name matching applies only to an architecture with no "flow" key (a call that points
    at a fixed graph itself, or old canvas JSON) — an architecture built by archfile.parse_arch
    always has a "flow" key (the original mermaid string, for frontend rendering).
    Without this distinction, the moment a user's arch.yaml happens to have name:
    gsm8k-treatment/-baseline
    (the deployed file's name is "GSM8K Treatment" — differing only in case)
    the whole file is ignored and the fixed graph runs instead, with no warning (item 4).
    """
    arch_name = (architecture.get("metadata") or {}).get("name", "")
    merged = {**DEFAULT_MODEL_CFG, **model_cfg}
    is_fixed_graph_candidate = "flow" not in architecture

    if is_fixed_graph_candidate and arch_name == "gsm8k-baseline":
        model = build_model(_model_settings(merged))
        from graphs.baseline import build_baseline

        return build_baseline(model=model, emit=emit, run_id=run_id)
    elif is_fixed_graph_candidate and arch_name == "gsm8k-treatment":
        model = build_model(_model_settings(merged))
        from graphs.treatment import build_treatment

        return build_treatment(model=model, emit=emit, run_id=run_id)
    else:
        from graphs.compile import compile_graph

        return compile_graph(architecture, merged, emit, run_id)


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

    # The graph is no longer paused, so it need not be a resume target —
    # leaving it in active_runs would pile up graph instances without bound.
    active_runs.pop(run_id, None)

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

# run_id → graph instance (for resume)
active_runs: dict[str, Any] = {}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()
    current_run_id: str | None = None

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("kind")

            if kind == "run":
                input_data = msg.get("input") or {}
                model_cfg = msg.get("model") or {}

                run_id = str(uuid.uuid4())
                current_run_id = run_id
                history: list = []
                run_history[run_id] = history
                while len(run_history) > MAX_RUN_HISTORY:
                    oldest_id = next(iter(run_history))
                    del run_history[oldest_id]
                    active_runs.pop(oldest_id, None)

                emitter = WSEventEmitter(ws, run_id, history)
                await safe_send_json(ws, {"kind": "run_started", "runId": run_id})

                try:
                    # architecture (canvas JSON) and archFile (a server/arch/*.yaml name) are
                    # mutually exclusive — if architecture is explicit (not null), it takes
                    # precedence.
                    # ArchError/ValueError/FileNotFoundError are handled in the except below.
                    arch = msg.get("architecture")
                    if arch is None and msg.get("archFile"):
                        arch = arch_files.read_arch_file(msg["archFile"])["architecture"]
                    arch = arch or {}

                    graph = dispatch_graph(arch, model_cfg, emitter, run_id)
                    active_runs[run_id] = graph

                    state0 = initial_state(
                        task=input_data.get("task", ""),
                        task_tags=input_data.get("task_tags", []),
                        batch_mode=False,
                        intent=input_data.get("intent"),
                        criteria=input_data.get("criteria"),
                    )
                    config = {
                        "configurable": {"thread_id": run_id},
                        "recursion_limit": RECURSION_LIMIT,
                    }
                    final = await graph.ainvoke(state0, config=config)
                    await _send_run_outcome(ws, run_id, final, history)
                except FileNotFoundError:
                    active_runs.pop(run_id, None)
                    message = f"arch file not found: {msg.get('archFile')}"
                    logger.warning("run %s rejected: %s", run_id, message)
                    await safe_send_json(ws, {"kind": "error", "runId": run_id, "message": message})
                except ValueError as e:
                    active_runs.pop(run_id, None)
                    logger.warning("run %s rejected: %s", run_id, e)
                    await safe_send_json(ws, {"kind": "error", "runId": run_id, "message": str(e)})
                except Exception as e:
                    active_runs.pop(run_id, None)
                    logger.exception("run %s failed", run_id)
                    await safe_send_json(
                        ws,
                        {
                            "kind": "error",
                            "runId": run_id,
                            "message": f"Execution error: {e}",
                        },
                    )

            elif kind == "resume":
                run_id = msg.get("runId") or current_run_id
                decision = msg.get("decision") or {}
                graph = active_runs.get(run_id)

                if not graph:
                    await safe_send_json(
                        ws,
                        {
                            "kind": "error",
                            "runId": run_id,
                            "message": "Run not found",
                        },
                    )
                    continue

                from langgraph.types import Command

                config = {
                    "configurable": {"thread_id": run_id},
                    "recursion_limit": RECURSION_LIMIT,
                }
                try:
                    final = await graph.ainvoke(Command(resume=decision), config=config)
                    resume_history = run_history.get(run_id) or []
                    await _send_run_outcome(ws, run_id, final, resume_history)
                except Exception as e:
                    active_runs.pop(run_id, None)
                    logger.exception("resume of run %s failed", run_id)
                    await safe_send_json(ws, {"kind": "error", "runId": run_id, "message": str(e)})

            elif kind == "reconnect":
                run_id = msg.get("runId", "")
                history = run_history.get(run_id, [])
                snapshot = [ev.to_frontend() for ev in history]
                await safe_send_json(ws, {"kind": "state", "runId": run_id, "snapshot": snapshot})

    except WebSocketDisconnect:
        pass
