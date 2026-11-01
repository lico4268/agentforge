# Agentforge UI

Optional read-only dashboard for AgentForge. Pick an `arch.yaml` from
`server/arch/`, enter a task, and run it: the `flow:` is rendered as a Mermaid
diagram, nodes are colored as they run, and human checkpoints can be answered
in the browser. Authoring happens in the YAML, not here.

## Run

```bash
npm install
npm run dev        # http://localhost:5137
npm run build      # type-check (tsc -b) + production build
npm run test       # vitest
npm run lint       # oxlint
```

Or start backend and frontend together with `../start.sh`.

Without `VITE_WS_URL` in `ui/.env`, the dashboard uses `MockTransport`, which
replays canned events so the UI works without a backend. Copy `.env.example`
to `.env` to connect to the real backend through the Vite proxy (`/ws` → `:8000`).

## Structure

```
src/
  app/          Dashboard, FlowDiagram (Mermaid), NodeProgress
  panels/       LogPanel, Markdown renderer
  execution/    Execution state (useExecutionStore + eventReducer)
  transport/    Transport interface + MockTransport / WebSocketTransport
  registry/     REST clients (arch files, models, run files, OpenRouter catalog)
  types/        Zod contracts mirroring the backend (arch, events)
```

Backend payloads are camelCase and parsed with the Zod schemas in `src/types/`;
see `../AGENTS.md` §4.
