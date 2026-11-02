# Agentforge

A tool for building LLM agent pipelines as text (`arch.yaml`) and running/testing them in
place. Authoring is a YAML file, and the diagram (mermaid) is a read-only artifact generated
automatically from that text — the old approach of building by drawing on a node canvas
(ComfyUI style) was retired in the 2026-09-02 text-first switch.

> **[DIRECTION.md](./DIRECTION.md) takes top priority for design direction and holds the roadmap** — if another document conflicts with it, that document is out of date.
> Local, untracked material (`docs/`, `refer_data/`, `work/`, `POLICY_*.md`, `ROADMAP.md`) is historical or working notes, not the current design.
> Coding, lint, import, and type contract rules follow [AGENTS.md](./AGENTS.md).

---

## Directory structure

```
agentforge/
├── config.yaml              # Central config (server, model list, run parameters, UI). Loaded by config.py
├── server/                  # FastAPI backend (Python 3.12)
│   ├── main.py              # FastAPI app for the dashboard: CORS, REST, WebSocket (runs via runner)
│   ├── manifests.py         # builtin node manifests (dicts) — runtime per node type, read by compile.py
│   ├── models.py            # ModelSettings/CallPolicy + build_model factory
│   ├── state.py             # AgentState (TypedDict) definition and initial_state
│   ├── events.py            # ExecutionEvent + make_event/make_error_event + WS/List emitter
│   ├── logging_config.py    # setup_logging() / logger (based on config.LOG_LEVEL)
│   ├── workspace.py         # Run artifacts under workspace/<run_id>/: run.json, events.jsonl, per-node .md
│   ├── config.py            # Loads config.yaml + .env (API keys)
│   ├── cli.py               # `agentforge` CLI — check/run/resume/replay/show/eval/compare (exit 0 done / 3 paused / 1 error)
│   ├── runner.py            # Shared start/resume/replay core (SQLite checkpointer) + run summary, used by CLI and server
│   ├── evaluate.py          # agentforge eval/compare — eval: block, graders, dataset runs, reports
│   ├── replay.py            # Pick the node a replay starts from; refuse flow changes; reuse stats
│   ├── archfile.py           # parse_arch — arch.yaml (mermaid flow + node defs) → Architecture dict
│   ├── arch_files.py         # List/read server/arch/*.yaml (file-based, GET /api/arch[/​{name}])
│   ├── arch/                 # Human-authored arch.yaml files (e.g. gsm8k.yaml)
│   ├── gitfiles.py          # Git plumbing for agent files/ (per-visit commits, --repo worktrees, replay clones)
│   ├── agent_tools/         # Commands mounted on the agent sandbox PATH (search → Tavily)
│   ├── nodes/               # Node helpers called by graphs (not a NodeRegistry — __init__.py is an empty package marker)
│   │   ├── llm_step.py      # run_llm_step — structured-output LLM call helper
│   │   ├── agent_step.py    # make_agent_node — `run: agent`: mini-swe-agent loop, commands in bwrap
│   │   ├── checkpoint.py    # make_human_checkpoint — interrupt-based human review
│   │   └── loop_guard.py    # pure guard evaluation for loop.guard nodes
│   └── graphs/              # LangGraph StateGraph definitions (the actual execution engine)
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
│       │   ├── LogPanel.tsx  # Run event log + workspace file viewer
│       │   └── Markdown.tsx  # react-markdown + remark-gfm renderer (LogPanel output display)
│       ├── transport/        # WebSocket / MockTransport abstraction layer
│       │   └── TransportContext.tsx  # Switch point between MockTransport ↔ WebSocketTransport
│       ├── types/            # Zod schemas (1:1 with backend Pydantic)
│       │   ├── arch.ts       # ArchGraphSchema etc. — mirrors archfile.py's Architecture dict
│       │   └── events.ts     # ExecutionEventSchema — mirrors events.py to_frontend()
│       ├── registry/         # Backend REST fetch helpers
│       │   ├── loadArchFiles.ts  # Fetch + parse GET /api/arch[/​{name}]
│       │   ├── loadRunFiles.ts   # Fetch + parse GET /api/runs/{id}/files
│       │   └── loadModels.ts / loadOpenRouterCatalog.ts  # GET /api/models, /api/openrouter/*
│       └── execution/        # Execution flow hooks/context
│
├── refer_data/              # Local only (gitignored): planning documents and reference papers (read-only)
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
OPENAI_API_KEY=...           # optional — only the providers you use
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

### Run

```bash
./start.sh
```

Starts the backend (FastAPI) and frontend (Vite) together. `Ctrl+C` stops both. `agentforge serve` does the same.

Headless CLI (no servers): `agentforge check|run|resume|replay|show|eval|compare` — see `skills/agentforge/SKILL.md`.
`run`/`resume` exit 0 when done, 3 when paused at a human checkpoint, 1 on error.

| Process | URL | Environment |
|---------|-----|-------------|
| Backend (FastAPI/uvicorn) | http://localhost:8000 | `server/.venv` (Python 3.12) |
| Frontend (Vite) | http://localhost:5137 | `ui/node_modules` (Node.js) |

### Running individually

```bash
# Backend only
cd server && .venv/bin/uvicorn main:app --reload --port 8000

# Frontend only
cd ui && npm run dev -- --port 5137
```

### Adding dependencies

```bash
# Python (backend)
cd server && .venv/bin/pip install <package>
# or edit pyproject.toml, then: uv pip install -e ".[dev]"

# Node (frontend)
cd ui && npm install <package>
```

---

## Core integration flow

CLI path (main use, from Claude Code via the skill):

```
server/arch/*.yaml → cli.py → archfile.parse_arch → runner.start_run/resume_run/replay_run
    → graphs.compile_graph (SQLite checkpointer at server/workspace/checkpoints.sqlite)
    → FileEventEmitter → server/workspace/<run_id>/ (run.json, events.jsonl, per-node .md)
```

Dashboard path (optional viewer):

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
runner.start_run → compile_graph (graphs/compile.py) → LangGraph StateGraph
    │ graph.ainvoke(state0)
    ▼
Each node function → emit(make_event(...)) → WSEventEmitter → WS stream + workspace files
    │
    ▼
Frontend FlowDiagram (passes architecture.flow straight to mermaid) coloring +
NodeProgress list updates (running / done / failed / paused / skipped)
```

**MockTransport vs WebSocketTransport**: `ui/src/transport/TransportContext.tsx` uses the real backend when
`VITE_WS_URL` is set in `ui/.env` (see `ui/.env.example`), and `MockTransport` otherwise.

---

## Using refer_data (local only)

- `refer_data/docs/` — early planning documents. Use as reference, but anything that conflicts with `DIRECTION.md` (fixed node roles, fixed branch names `accept`/`refine`/`clarify`) is **void**.
- `refer_data/papers/` — consult the reference papers when making algorithm/architecture design decisions.
- This folder is **read-only** and serves as source material for code generation. Do not modify it.

---

## Development rules

- Type contract: backend Pydantic field names are **unified in camelCase** with the frontend Zod schemas (no snake_case conversion).
- Adding nodes: when a user writes a new node in arch.yaml, `archfile.py` emits it as `custom.node` (runtime `llm_step`), so most of the time there is no need to touch manifests. Only when you truly need a new **runtime** (execution logic with a different input/output contract), create a helper function in `server/nodes/` (e.g. the `run_llm_step` pattern), add a manifest (dict) to `BUILTIN_MANIFESTS` in `server/manifests.py`, and branch on that `runtime` key in `graphs/compile.py`. (Not the old `NodeBase`/`NodeRegistry` approach — those rules are retired. There is no frontend node palette either — the diagram is auto-generated mermaid, so there is nothing on the frontend to register a manifest with.)
- Event `output` field: shown as-is as JSON/Markdown in the frontend `NodeProgress`/`LogPanel`, and every event is persisted under `server/workspace/<run_id>/` (`events.jsonl`, plus a `.md` per `node_end` output) by `WSEventEmitter`/`FileEventEmitter`, so only put serializable values in it (`str`, `dict`, `list`).
- The execution engine is LangGraph `StateGraph`, built by `compile_graph(architecture)` from what `archfile.parse_arch(arch.yaml)` returns. For what remains, see the roadmap in DIRECTION.md §5.
