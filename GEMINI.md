# Agentforge — Gemini Context

> The single source of coding, lint, import, and type contract rules is **AGENTS.md**. Read it first.
> For project structure and environment setup, see **CLAUDE.md**.

---

## Project summary

A ComfyUI-style agent architecture builder. Visually design and run LLM agent pipelines on a node canvas.

- **Backend**: FastAPI + LangGraph (Python 3.12, `server/`)
- **Frontend**: React + TypeScript + Vite (`ui/`)
- **WebSocket integration**: `ws://localhost:8000/ws/run`

```
Frontend canvas (React Flow)
    │ WebSocket
    ▼
Backend WS handler (main.py)
    │ dispatch_graph(arch_name)
    ▼
LangGraph StateGraph (graphs/*.py)
    │ emit(make_event(...))
    ▼
Frontend node status update
```

---

## Current progress (as of 2026-07-03)

- **v0.1**: nearly done. One manual E2E check remaining (after the ANTHROPIC_API_KEY 401 is resolved)
- **v0.2**: done (governance/ruff/tests/error and logging standardization)
- **v0.3**: not started. Core = implement `compile_graph(architecture: dict)`
  - `dispatch_graph` at `server/main.py:110` is the blocking point
  - Selecting `current canvas` raises ValueError — this is the seam

### v0.3 entry point

```python
# around server/main.py:110
# need to wire a compile_graph fallback into dispatch_graph(arch_name)
```

---

## Key design decisions (do not change)

### Policy node (Phase 1 implemented, uncommitted)
- `confidence` self-scoring routing **retired** → intent-alignment review based on `ReviewDelta`
- `review_branch` field: `accept` / `refine` / `clarify`
- No `score` field — prevents confidence from creeping back in
- Related files: `server/nodes/review.py`, `server/nodes/policy.py`, `server/models.py`

### Type contract
- Backend Pydantic ↔ frontend Zod schemas: **unified camelCase** (no snake_case conversion layer)
- WS payloads go out through `to_frontend()` in `events.py`

### Adding nodes
- **Retired approach**: `NodeBase` / `NodeRegistry` (no implementation)
- **Current approach**: function in `server/nodes/` → `StateGraph.add_node()` in `server/graphs/`
- Frontend: add a manifest (dict) to `BUILTIN_MANIFESTS` in `server/manifests.py`

---

## Development environment

```bash
./start.sh          # start backend (8000) + frontend (5137) together
```

Environment variables: `ANTHROPIC_API_KEY` is required in `server/.env`.

---

## Do not

- Restore `confidence`-based routing (retired design)
- Add nodes via the `NodeBase` / `NodeRegistry` approach
- Add a snake_case ↔ camelCase conversion layer
- Use `print()` (use `from logging_config import logger` instead)
- Leave only `# TODO` / `# removed` comments without code
