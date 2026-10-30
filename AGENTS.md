# AGENTS.md

The single source of **rules that AI coding agents (Claude Code, Cursor, Antigravity, etc.) always follow when writing or modifying code in this repository**.
For architecture, directory layout, and how to run things, see [CLAUDE.md](./CLAUDE.md); for progress, see [ROADMAP.md](./ROADMAP.md).

---

## 1. Paths

- Always use **absolute paths** when referencing files or calling tools.
- Do not rely on assumptions about the working directory (no `cd` followed by relative paths ❌).

## 2. Verify after changes (required)

If you changed code, you **must run** the checks for that area before committing or reporting completion.

| Area | Command (run in that directory) |
|------|----------------------------------|
| Backend (`server/`) | `ruff check .` → `ruff format .` |
| Frontend (`ui/`) | `npm run lint` (oxlint) → type-check with `npm run build` (`tsc -b`) |
| Tests | Backend `pytest`, frontend `npm run test` (once introduced) |

- Leave no lint errors. Clean up auto-fixable items with `ruff check --fix`.

## 3. Import order

- **Backend**: follow ruff's isort rules (`I`) — standard library → third-party → local, with a blank line between groups. `ruff check --fix` sorts them.
- **Frontend**: follow oxlint, grouping external packages → internal modules (`@/…` or relative paths).

## 4. Type contract (backend ↔ frontend)

- Backend Pydantic field names and frontend Zod schemas are **unified in camelCase**. Do not add a snake_case ↔ camelCase conversion layer.
- Payloads sent over WebSocket go through `to_frontend()` (camelCase) in `events.py`. When adding a field, update the backend serialization and the Zod schemas in `ui/src/types/` **at the same time**.

## 5. Adding nodes

> The execution engine is LangGraph `StateGraph`. The old `NodeBase`/`NodeRegistry` approach is deprecated (`server/nodes/__init__.py` is an empty package marker).

- **Backend execution**: create a node helper function in `server/nodes/` (e.g. the `run_llm_step`/`make_human_checkpoint` pattern) and wire it with `graph.add_node(...)` in a graph builder under `server/graphs/`. Handle branching with `add_conditional_edges` + a pure routing function like those in `policy.py`.
- **Frontend exposure**: add a manifest (dict) to `BUILTIN_MANIFESTS` in `server/manifests.py`. `GET /api/nodes` returns it, and the frontend `NodeRegistry` (`ui/src/registry/`) receives it to render the palette, canvas, and Inspector.
- The event `output` field is shown as-is as JSON in the Inspector, so only put serializable values in it (`str`, `dict`, `list`).

## 6. Tests (recommended)

- When adding or changing a feature, **include tests in the same PR** where possible. Backend: `server/tests/` (pytest); frontend: `ui/src/__tests__/` (vitest).
- **Mock** external LLM API calls in tests. Do not write tests that depend on the network or real API keys.

## 7. Errors and logging (standardized)

- Do not handle node execution failures ad hoc; emit them with `events.make_error_event(run_id, node_id, exc)`. This produces `event_type="error"` plus a structured `error={"type", "detail"}` field. The frontend `eventReducer` maps `'error'` → node status `'failed'`, and `LogPanel` displays `error.detail`.
- When adding or changing the `error` field, update both the backend `to_frontend()` and `ExecutionErrorSchema` in the frontend `ui/src/types/events.ts` (§4 type contract).
- Do not use `print`. Use `from logging_config import logger`; at app startup, `setup_logging()` initializes it based on `config.LOG_LEVEL`.
