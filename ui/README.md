# Agentforge UI

ComfyUI-style node canvas for designing agent cognitive architectures.
Design rationale: [../ui-architecture.md](../ui-architecture.md).

## Run

```bash
npm install        # first time (uses ../.npm-cache locally)
npm run dev        # http://localhost:5137
npm run build      # type-check + production build
```

No backend needed yet — `MockTransport` replays execution events so the live
canvas works standalone. Press **Run** to watch nodes highlight.

## Structure (see ui-architecture.md §3)

```
src/
  types/        Zod contracts shared with the backend (manifest, graph, events)
  registry/     Node registry — manifests drive rendering (extensibility core)
  transport/    Transport interface + MockTransport / WebSocketTransport
  stores/       Topology state (useGraphStore) — what the user draws
  execution/    Execution state (useExecutionStore) — backend event stream
  canvas/       React Flow canvas + GenericNode (manifest-driven node)
  panels/       NodeLibrary · Inspector · LogPanel
  app/          Shell: providers, layout, toolbar, starter graph
```

## Two rules that hold the design together

1. **Topology state ≠ execution state.** Editing and the high-frequency event
   stream live in separate stores; nodes subscribe to their own runtime so a
   single event re-renders only that node.
2. **Nodes are data-driven.** `GenericNode` renders any node from its manifest.
   Adding a node = adding a manifest (`registry/builtinManifests.ts`, or the
   backend serving `/api/nodes`). No component changes.

## Wiring the backend later

Swap `MockTransport` for `WebSocketTransport` in
`src/transport/TransportContext.tsx`. Nothing else changes — the protocol and
event types are already defined in `src/transport/protocol.ts` and `src/types/`.
