# Agentforge

A tool for building LLM agent pipelines as text (`arch.yaml`) and running/testing them in
place. Authoring is a YAML file, and the diagram (mermaid) is a read-only artifact generated
automatically from that text — the old approach of building by drawing on a node canvas
(ComfyUI style) was retired in the 2026-09-02 text-first switch.

> **[DIRECTION.md](./DIRECTION.md) takes top priority for design direction** — if another document conflicts with it, that document is out of date.
> `docs/superpowers/**`, `work/**`, and `POLICY_*.md` are historical records, not the current design.
> Coding, lint, import, and type contract rules follow [AGENTS.md](./AGENTS.md). For progress, see [ROADMAP.md](./ROADMAP.md).

---

## Directory structure

```
agentforge/
├── config.yaml              # Central config (server, model list, run parameters, UI). Loaded by config.py
├── server/                  # FastAPI backend (Python 3.12)
│   ├── main.py              # FastAPI app entry point, CORS, REST, WebSocket, dispatch_graph
│   ├── manifests.py         # GET /api/nodes — list of builtin node manifests (dicts)
│   ├── models.py            # LLM output schemas (PlanOut/ReasonOut/Criterion/ReviewDelta) + build_model factory
│   ├── state.py             # AgentState (TypedDict) definition and initial_state
│   ├── events.py            # ExecutionEvent + make_event/make_error_event + WS/List emitter
│   ├── logging_config.py    # setup_logging() / logger (based on config.LOG_LEVEL)
│   ├── harness.py           # Benchmark harness (run_dataset + gsm8k_grader + Report) — measures pass@1
│   ├── workspace.py         # Run artifacts — saves/reads node_end output as workspace/<run_id>/*.md
│   ├── config.py            # Loads config.yaml + .env (API keys)
│   ├── cli.py               # `agentforge` CLI — check/run/resume/replay/show (exit 0 done / 3 paused / 1 error)
│   ├── runner.py            # Shared start/resume core (SQLite checkpointer) used by CLI and server
│   ├── archfile.py           # parse_arch — arch.yaml (mermaid flow + node defs) → Architecture dict
│   ├── arch_files.py         # List/read server/arch/*.yaml (file-based, GET /api/arch[/​{name}])
│   ├── arch/                 # Human-authored arch.yaml files (e.g. gsm8k.yaml)
│   ├── nodes/               # Node helpers called by graphs (not a NodeRegistry — __init__.py is an empty package marker)
│   │   ├── llm_step.py      # run_llm_step — structured-output LLM call helper
│   │   ├── checkpoint.py    # make_human_checkpoint — interrupt-based human review
│   │   ├── review.py        # make_review — intent×criteria review (produces ReviewDelta, used only by treatment.py)
│   │   └── policy.py        # compute_review_branch / make_route_review — pure routing functions
│   └── graphs/              # LangGraph StateGraph definitions (the actual execution engine)
│       ├── baseline.py      # build_baseline — single-shot baseline that only does Reasoning
│       ├── treatment.py     # build_treatment — Planning→Reasoning→Policy three-way structure
│       └── compile.py       # compile_graph — dynamically compiles the Architecture dict that parse_arch builds from arch.yaml
│
├── ui/                      # React + TypeScript frontend (Vite)
│   └── src/
│       ├── App.tsx           # Root component — renders <Dashboard />
│       ├── app/
│       │   ├── Dashboard.tsx            # Read-only dashboard — pick arch.yaml, Run, approve/reject checkpoints
│       │   ├── FlowDiagram.tsx          # Renders architecture.flow (mermaid string) as-is + colors nodes during a run
│       │   └── NodeProgress.tsx         # Lists run events as per-node visits
│       ├── panels/
│       │   └── Markdown.tsx  # react-markdown + remark-gfm renderer (LogPanel output display)
│       ├── transport/        # WebSocket / MockTransport abstraction layer
│       │   └── TransportContext.tsx  # Switch point between MockTransport ↔ WebSocketTransport
│       ├── types/            # Zod schemas (1:1 with backend Pydantic)
│       │   ├── arch.ts       # ArchGraphSchema etc. — mirrors archfile.py's Architecture dict
│       │   └── workspace.ts  # Zod schemas for run file list/content (mirrors workspace.py REST)
│       ├── registry/         # Backend REST fetch helpers
│       │   ├── loadArchFiles.ts  # Fetch + parse GET /api/arch[/​{name}]
│       │   └── loadRunFiles.ts   # Fetch + parse GET /api/runs/{id}/files
│       └── execution/        # Execution flow hooks/context
│
├── refer_data/              # Planning documents and reference material (read-only)
│   ├── docs/                # Project plan and design specs
│   │   ├── agentforge.md    # Overall project plan
│   │   ├── backend-spec.md  # Detailed backend spec
│   │   ├── node-spec.md     # Detailed node type spec
│   │   ├── ui-architecture.md  # UI architecture design
│   │   └── v0.1-validation.md  # v0.1 validation criteria
│   └── papers/              # Reference papers
│       ├── AgentFlow (Stanford, 2025).pdf
│       ├── Agentic Auto-Scheduling.pdf
│       ├── CCA (Cognitive Control Architecture) 2025.pdf
│       └── CoALA (Cognitive Architectures for Language Agents) 2023.pdf
│
├── backend-architecture.md  # Detailed backend design & frontend integration document
├── agentforge               # Repo-root wrapper: `agentforge serve` → start.sh, anything else → server/cli.py
├── skills/agentforge/       # Claude Code skill (SKILL.md) that drives the CLI
├── start.sh                 # Combined dev server startup script
└── CLAUDE.md                # This file
```

---

## Local development setup

### Prerequisites

- Python 3.12
- Node.js (system install)
- `uv` package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Environment variables

Set API keys in `server/.env` (if missing, start.sh copies it from `.env.example` automatically):

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # optional
DATABASE_URL=sqlite:///./agentforge.db
```

### Run

```bash
./start.sh
```

Starts the backend (FastAPI) and frontend (Vite) together. `Ctrl+C` stops both. `agentforge serve` does the same.

Headless CLI (no servers): `agentforge check|run|resume|replay|show` — see `skills/agentforge/SKILL.md`.
`run`/`resume` exit 0 when done, 3 when paused at a human checkpoint, 1 on error.

| Process | URL | Environment |
|---------|-----|-------------|
| Backend (FastAPI/uvicorn) | http://localhost:8000 | `server/.venv` (Python 3.12) |
| Frontend (Vite) | http://localhost:5137 | `ui/node_modules` (Node.js) |

### Running individually

```bash
# Backend only
cd server && ../.venv/bin/uvicorn main:app --reload --port 8000

# Frontend only
cd ui && npm run dev -- --port 5137
```

### Adding dependencies

```bash
# Python (backend)
cd server && ../server/.venv/bin/pip install <package>
# or edit pyproject.toml, then: uv pip install -e ".[dev]"

# Node (frontend)
cd ui && npm install <package>
```

---

## Core integration flow

```
A human writes server/arch/*.yaml
    │
Frontend Dashboard (pick from the arch.yaml list + enter a task + Run)
    │ WebSocket ws://localhost:8000/ws/run
    ▼
Backend WS handler (main.py: ws_run)
    │ { kind: "run", archFile: "<name>.yaml", input, model }
    ▼
archfile.parse_arch(yaml_text) → Architecture dict (nodes/edges/flow)
    │
dispatch_graph(architecture) → LangGraph StateGraph builder in graphs/*.py
    │ graph.ainvoke(state0)
    ▼
Each node function → emit(make_event(...)) → WSEventEmitter → WS stream
    │
    ▼
Frontend FlowDiagram (passes architecture.flow straight to mermaid) coloring +
NodeProgress list updates (running / done / failed / paused / skipped)
```

> `dispatch_graph` dispatches to a fixed graph builder for the fixed arch names (`gsm8k-baseline`/`gsm8k-treatment`);
> otherwise it falls back to `compile_graph(architecture)` (`graphs/compile.py`), which compiles the parsed graph
> directly into a `StateGraph` and runs it (v0.3, commit `faa736e`). The only thing the 2026-09-02 text-first switch
> changed is that `architecture` is now built by `archfile.parse_arch` instead of the canvas — `compile_graph` itself
> is unchanged. For limitations and remaining verification, see ROADMAP.

**Switching MockTransport → WebSocketTransport**: a one-line change in `ui/src/transport/TransportContext.tsx`.

---

## Using refer_data

- `refer_data/docs/` — early planning documents. Use as reference, but anything that conflicts with `DIRECTION.md` (fixed node roles, fixed branch names `accept`/`refine`/`clarify`) is **void**.
- `refer_data/papers/` — consult the reference papers when making algorithm/architecture design decisions.
- This folder is **read-only** and serves as source material for code generation. Do not modify it.

---

## Development rules

- Type contract: backend Pydantic field names are **unified in camelCase** with the frontend Zod schemas (no snake_case conversion).
- Adding nodes: when a user writes a new node in arch.yaml, `archfile.py` emits it as `custom.node` (runtime `llm_step`), so most of the time there is no need to touch manifests. Only when you truly need a new **runtime** (execution logic with a different input/output contract), create a helper function in `server/nodes/` (e.g. the `run_llm_step` pattern), add a manifest (dict) to `BUILTIN_MANIFESTS` in `server/manifests.py`, and branch on that `runtime` key in `graphs/compile.py`. (Not the old `NodeBase`/`NodeRegistry` approach — those rules are retired. There is no frontend node palette either — the diagram is auto-generated mermaid, so there is nothing on the frontend to register a manifest with.)
- Event `output` field: shown as-is as JSON/Markdown in the frontend `NodeProgress`/`LogPanel`, and `node_end` output is automatically persisted by `WSEventEmitter` as `.md` files under `server/workspace/<run_id>/`, so only put serializable values in it (`str`, `dict`, `list`).
- The execution engine has been LangGraph `StateGraph` since v0.1. v0.3's dynamic compilation (`compile_graph(architecture)`) is implemented — only the source of `architecture` changed on 2026-09-02, from the canvas to `archfile.parse_arch(arch.yaml)`. For what remains, see ROADMAP.
