import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import config as cfg
from events import WSEventEmitter
from logging_config import logger, setup_logging
from manifests import BUILTIN_MANIFESTS
from models import build_model
from state import initial_state

setup_logging()
app = FastAPI(title="Agentforge Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 모델 목록 ───────────────────────────────────────────────────────────────────


def _load_models_config() -> list[dict]:
    """config.yaml models.list에서 enabled 모델만 반환.
    API 키 미설정 provider는 available=False 표시."""
    key_by_provider = {
        "anthropic": bool(cfg.ANTHROPIC_API_KEY),
        "openai": bool(cfg.OPENAI_API_KEY),
        "google": bool(cfg.GOOGLE_API_KEY),
        "local": True,
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
    return result


# ─── 아키텍처 파일 저장소 (v0.1 파일 기반) ─────────────────────────────────────

ARCH_DIR = Path(__file__).parent / "architectures"
ARCH_DIR.mkdir(exist_ok=True)

# ─── REST 엔드포인트 ─────────────────────────────────────────────────────────────


@app.get("/api/models")
async def get_models() -> list[dict]:
    """models_config.json 기반 모델 목록. available 필드로 API 키 설정 여부 표시."""
    return _load_models_config()


@app.get("/api/nodes")
async def get_nodes() -> list[dict]:
    return BUILTIN_MANIFESTS


@app.get("/api/architectures")
async def list_architectures() -> list[dict]:
    result = []
    for f in ARCH_DIR.glob("*.json"):
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return result


@app.post("/api/architectures")
async def save_architecture(body: dict) -> dict:
    arch_id = body.get("id") or str(uuid.uuid4())
    body["id"] = arch_id
    path = ARCH_DIR / f"{arch_id}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2))
    return body


@app.get("/api/architectures/{arch_id}")
async def get_architecture(arch_id: str) -> dict:
    path = ARCH_DIR / f"{arch_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Architecture not found")
    return json.loads(path.read_text())


# ─── 워크스페이스 파일 (run output 영속화) ───────────────────────────────────────


@app.get("/api/runs/{run_id}/files")
async def list_run_files(run_id: str) -> list[dict]:
    """run_id 디렉토리의 노드 output 파일 목록 (camelCase)."""
    from workspace import list_run_files as _list

    return _list(run_id)


@app.get("/api/runs/{run_id}/files/{name}")
async def read_run_file(run_id: str, name: str) -> dict:
    """단일 워크스페이스 파일 내용."""
    from workspace import read_run_file as _read

    result = _read(run_id, name)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result


# ─── 그래프 디스패처 ─────────────────────────────────────────────────────────────

DEFAULT_MODEL_CFG = {
    "provider": "google",
    "model": "gemini-3.1-flash-lite",
    "temperature": 0.0,
}


def dispatch_graph(architecture: dict, model_cfg: dict, emit: Any, run_id: str):
    """
    v0.1: 'gsm8k-baseline'/'gsm8k-treatment' 이름은 고정 그래프 빌더에 디스패치.
    v0.3: 그 외는 compile_graph(architecture)로 캔버스를 직접 컴파일 (§8 seam).
    """
    arch_name = (architecture.get("metadata") or {}).get("name", "")
    cfg = {**DEFAULT_MODEL_CFG, **model_cfg}

    if arch_name == "gsm8k-baseline":
        model = build_model(cfg["provider"], cfg["model"], float(cfg["temperature"]))
        from graphs.baseline import build_baseline

        return build_baseline(model=model, emit=emit, run_id=run_id)
    elif arch_name == "gsm8k-treatment":
        model = build_model(cfg["provider"], cfg["model"], float(cfg["temperature"]))
        from graphs.treatment import build_treatment

        return build_treatment(model=model, emit=emit, run_id=run_id)
    else:
        from graphs.compile import compile_graph

        return compile_graph(architecture, cfg, emit, run_id)


async def _send_run_outcome(ws, run_id: str, final: dict, history: list) -> None:
    """graph.ainvoke() 결과가 interrupt로 인한 일시정지인지, 정상 완료인지 구분해서 보낸다.

    LangGraph는 interrupt() 호출 시 예외 없이 final state에 "__interrupt__" 키를 채워
    반환한다 — 이를 확인하지 않으면 일시정지를 완료로 오인해 run_complete(answer=null)을
    보내게 되고, 프론트는 그래프가 실제로는 대기 중인데도 실행이 끝난 것으로 표시한다.
    """
    if final.get("__interrupt__"):
        last_interrupt = next(
            (e for e in reversed(history) if e.event_type == "interrupt"),
            None,
        )
        await ws.send_json(
            {
                "kind": "interrupt",
                "runId": run_id,
                "nodeId": last_interrupt.node_id if last_interrupt else "",
                "payload": last_interrupt.output if last_interrupt else {},
            }
        )
        return

    # 그래프가 더 이상 일시정지되지 않았으니 resume 대상일 필요가 없다 —
    # active_runs에 남겨두면 그래프 인스턴스가 무한정 쌓인다.
    active_runs.pop(run_id, None)

    await ws.send_json(
        {
            "kind": "run_complete",
            "runId": run_id,
            "result": {
                "answer": final.get("answer"),
                "reviewDelta": final.get("review_delta"),
                "reviewBranch": final.get("review_branch"),
            },
        }
    )


# ─── WebSocket 실행 핸들러 ────────────────────────────────────────────────────────

# run_history에 보관할 최대 run 수 — 초과 시 가장 오래된 run부터 제거(무한 성장 방지)
MAX_RUN_HISTORY = 50

# run_id → 누적 이벤트 (재접속 시 재전송용)
run_history: dict[str, list] = {}

# run_id → 그래프 인스턴스 (resume용)
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
                arch = msg.get("architecture") or {}
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
                await ws.send_json({"kind": "run_started", "runId": run_id})

                try:
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
                        "recursion_limit": cfg.MAX_RETRIES * 10 + 20,
                    }
                    final = await graph.ainvoke(state0, config=config)
                    await _send_run_outcome(ws, run_id, final, history)
                except ValueError as e:
                    active_runs.pop(run_id, None)
                    logger.warning("run %s rejected: %s", run_id, e)
                    await ws.send_json({"kind": "error", "runId": run_id, "message": str(e)})
                except Exception as e:
                    active_runs.pop(run_id, None)
                    logger.exception("run %s failed", run_id)
                    await ws.send_json(
                        {
                            "kind": "error",
                            "runId": run_id,
                            "message": f"Execution error: {e}",
                        }
                    )

            elif kind == "resume":
                run_id = msg.get("runId") or current_run_id
                decision = msg.get("decision") or {}
                graph = active_runs.get(run_id)

                if not graph:
                    await ws.send_json(
                        {
                            "kind": "error",
                            "runId": run_id,
                            "message": "Run not found",
                        }
                    )
                    continue

                from langgraph.types import Command

                config = {
                    "configurable": {"thread_id": run_id},
                    "recursion_limit": cfg.MAX_RETRIES * 10 + 20,
                }
                try:
                    final = await graph.ainvoke(Command(resume=decision), config=config)
                    resume_history = run_history.get(run_id) or []
                    await _send_run_outcome(ws, run_id, final, resume_history)
                except Exception as e:
                    active_runs.pop(run_id, None)
                    logger.exception("resume of run %s failed", run_id)
                    await ws.send_json({"kind": "error", "runId": run_id, "message": str(e)})

            elif kind == "reconnect":
                run_id = msg.get("runId", "")
                history = run_history.get(run_id, [])
                snapshot = [ev.to_frontend() for ev in history]
                await ws.send_json({"kind": "state", "runId": run_id, "snapshot": snapshot})

    except WebSocketDisconnect:
        pass
