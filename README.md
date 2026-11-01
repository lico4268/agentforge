# AgentForge

AgentForge runs LLM agent pipelines defined in a short `arch.yaml`. It compiles the
YAML into a LangGraph `StateGraph`, runs it from a headless CLI or a browser
dashboard, and records per-node output, tokens, and cost.

It is built to be driven from Claude Code: Claude designs the pipeline as YAML, and
AgentForge runs it cheaply, repeatedly, and measurably — a different model per node,
replay from a middle node, and run records you can diff.

> Current stage: **CLI, skill, replay, honest cost, eval, compare, and `run: agent` nodes are done, including finer per-node sandbox rules (`files:`, `tools:`, memory/CPU limits).**
> See the roadmap in [DIRECTION.md](./DIRECTION.md#5-roadmap).

## Features

- Text-based agent definitions in `server/arch/*.yaml`
- Headless CLI: `agentforge check | run | resume | replay | show | eval | compare`
- Dataset evals from an `eval:` block: success rate, cost per success, per-node cost
- Side-by-side comparison of two variants with paired results and a noise warning
- Replay a run from the first changed node, reusing earlier nodes' outputs
- `run: agent` nodes: a mini-swe-agent bash loop in a bwrap sandbox (no network or secrets
  unless the node asks), working in a per-run git repo or a branch of your own repo
- Paused runs survive restarts (SQLite checkpointer shared by CLI and server)
- A Claude Code skill (`skills/agentforge/`) that drives the CLI
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

## Use the CLI

```bash
./agentforge check server/arch/gsm8k.yaml
./agentforge run server/arch/gsm8k.yaml --task "Tom has 3 apples and buys 4 more. How many?"
./agentforge show <run_id> [<node>]
```

`run` and `resume` exit `0` when done, `3` when paused at a human checkpoint, and `1`
on error. Answer a checkpoint with `./agentforge resume <run_id> --choice <label>`.
After editing a node's prompt or model, `./agentforge replay <run_id> --arch <file.yaml>`
re-runs from the first changed node. Each run is stored under
`server/workspace/<run_id>/` (`run.json`, `events.jsonl`, one `.md` per node output).

Add an `eval:` block (dataset + grader) to an `arch.yaml` and run
`./agentforge eval <file.yaml> --limit 5` to get the success rate, cost per success, and
per-node cost over a dataset; `server/arch/gsm8k.yaml` has one. Compare two variants on
the same items with `./agentforge compare a.yaml b.yaml`, or change one field in place:
`./agentforge compare server/arch/gsm8k.yaml --set model=anthropic/claude-haiku-4-5-20251001`.

An agent node (`run: agent`, see `server/arch/fib-agent.yaml`) lets a model run bash commands
in a sandbox until it submits an answer; it needs [bubblewrap](https://github.com/containers/bubblewrap)
(`bwrap`). Its files land in `server/workspace/<run_id>/files/`, a git repo with one commit per
agent visit. Add `--repo <path>` to `run` to work on a branch `agentforge/<run_id>` of an
existing repo instead; your checkout is never touched.

To use it from Claude Code, link the skill:

```bash
ln -s "$PWD/skills/agentforge" ~/.claude/skills/agentforge
```

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
outputs, and prompts for each LLM step. Optional node keys are `model`,
`temperature`, `max_tokens`, and `join: all|any` (required when a node has two or more
plain incoming edges). A node with multiple outgoing labels is treated as a branch node,
and `run: human.checkpoint` pauses for a person. Back edges are recognized as loops, and a guard is added
automatically to enforce the execution limit. Parsing errors appear in the
dashboard with the corresponding line number from the source YAML.

## How It Works

```text
server/arch/*.yaml
        │
        ▼
 archfile.parse_arch ──► Read-only Mermaid diagram (dashboard)
        │
        ▼
 graphs.compile_graph ◄── SQLite checkpointer (pause / resume / replay)
        │
        ▼
 LangGraph StateGraph ──► CLI summary, or WebSocket to the dashboard
        │
        ▼
 server/workspace/<run_id>/  (run.json, events.jsonl, per-node .md)
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
├── nodes/             # Node execution helpers (llm_step, agent_step, checkpoint, …)
├── agent_tools/       # Commands on the agent sandbox PATH (search)
├── gitfiles.py        # Git plumbing for agent files/ (commits, worktrees)
├── cli.py             # agentforge CLI
├── runner.py          # Shared start / resume / replay core
├── replay.py          # Replay start-node selection
├── workspace.py       # Persistent storage for run records and outputs
└── main.py            # FastAPI and WebSocket entry point

skills/agentforge/     # Claude Code skill

ui/src/
├── app/               # Dashboard, diagram, and progress views
├── execution/         # Execution state management
├── transport/         # WebSocket and mock transports
├── registry/          # REST API clients
└── types/             # Zod-based API contracts
```

## Current Scope and Next Steps

Text-based authoring, dynamic execution, branches, loops, Human Checkpoints, the CLI,
the Claude Code skill, replay, honest per-node cost, `eval:`, `compare`, and sandboxed
`run: agent` nodes are implemented, with finer per-node sandbox rules (`files:`, `tools:`,
memory/CPU limits). Next: see DIRECTION.md §6 (stale fixed-vocabulary code).

See [DIRECTION.md](./DIRECTION.md) for design principles and the roadmap, and
[AGENTS.md](./AGENTS.md) for development guidelines.
