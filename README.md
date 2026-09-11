# AgentForge

AgentForge is a local development tool for defining LLM agent pipelines in
`arch.yaml` and inspecting their structure and execution in the browser. It renders
the YAML `flow` as a Mermaid diagram and compiles the same definition into a
LangGraph `StateGraph` for execution.

> Current development stage: **v0.5 — text-first architecture migration complete**

## Features

- Text-based agent definitions in `server/arch/*.yaml`
- Read-only execution diagrams rendered with Mermaid
- Dynamic compilation of YAML architectures into LangGraph graphs
- Conditional branching based on LLM or human decisions
- Automatic feedback-loop detection and `loop.guard` insertion
- Real-time node status, logs, and results over WebSocket
- Human Checkpoints with pause, approve, edit, reject, and resume workflows
- Markdown persistence and retrieval for node outputs
- OpenRouter model catalog and favorites

## Quick Start

### Requirements

- Python 3.12
- Node.js and npm
- [`uv`](https://docs.astral.sh/uv/)

### Run

```bash
git clone <repository-url>
cd agentforge
./start.sh
```

On the first run, the script sets up the backend virtual environment and frontend
dependencies. Add the API keys for the models you want to use to the generated
`server/.env`, then run the script again.

```dotenv
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
```

Only the keys you need are required. Available models and defaults are configured
in `config.yaml`.

| Service | URL |
|---|---|
| Frontend | http://localhost:5137 |
| Backend | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |

`start.sh` runs both development servers and stops them together when you press
`Ctrl+C`. The frontend is also exposed to the LAN, so another device on the same
network can connect to port `5137` at the VM's address.

## Define an Architecture

Add a `.yaml` file under `server/arch/`. It will appear in the browser after a
refresh.

```yaml
name: GSM8K Treatment
model: google/gemini-3.1-flash-lite

flow: |
  input --> planning --> reasoning --> review
  review -->|ok| output
  review -->|retry| reasoning

nodes:
  planning:
    in: [task]
    out: [plan]
    prompt: |
      Break the problem into steps. Write one line per step.

  reasoning:
    in: [task, plan, feedback]
    out: [answer]
    prompt: |
      Follow the plan to solve the problem. On the final line, write only
      the numeric answer.

  review:
    in: [task, answer]
    out: [feedback]
    prompt: |
      Check whether the answer solves the problem. If it does, return ok.
      Otherwise, return retry and explain the error in feedback.
```

`flow` defines execution order and branches, while `nodes` defines the inputs,
outputs, and prompts for each LLM step. A node with multiple outgoing labels is
treated as a branch node. Back edges are recognized as loops, and a guard is added
automatically to enforce the execution limit. Parsing errors appear in the
dashboard with the corresponding line number from the source YAML.

## How It Works

```text
server/arch/*.yaml
        │
        ▼
 archfile.parse_arch ──► Read-only Mermaid diagram
        │
        ▼
 graphs.compile_graph
        │
        ▼
 LangGraph StateGraph ──WebSocket──► Status, logs, and results
```

The backend uses `FastAPI`, `LangGraph`, and `Pydantic`. The frontend is built with
`React`, `TypeScript`, `Vite`, and `Zod`.

## Development Commands

Backend:

```bash
cd server
.venv/bin/ruff check .
.venv/bin/ruff format .
.venv/bin/pytest
```

Frontend:

```bash
cd ui
npm run lint
npm run build
npm run test
```

## Project Structure

```text
server/
├── arch/              # User-authored arch.yaml files
├── archfile.py        # YAML and Mermaid flow parser
├── graphs/compile.py  # Dynamic LangGraph compiler
├── nodes/             # Node execution helpers
├── workspace.py       # Persistent storage for run outputs
└── main.py            # FastAPI and WebSocket entry point

ui/src/
├── app/               # Dashboard, diagram, and progress views
├── execution/         # Execution state management
├── transport/         # WebSocket and mock transports
├── registry/          # REST API clients
└── types/             # Zod-based API contracts
```

## Current Scope and Next Steps

Text-based authoring, dynamic execution, conditional branches, loops, and Human
Checkpoints are implemented. The main remaining work includes fully generalizing
arbitrary node composition, removing fixed policy vocabulary, adding an
architecture save/load interface, running large-scale GSM8K validation, and
integrating τ²-bench.

See [ROADMAP.md](./ROADMAP.md) for the current project status,
[DIRECTION.md](./DIRECTION.md) for design principles, and
[AGENTS.md](./AGENTS.md) for development guidelines.
