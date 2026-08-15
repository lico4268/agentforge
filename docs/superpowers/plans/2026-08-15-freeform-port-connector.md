# Freeform Port Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the always-rendered, index-based fallback port dots in connection edit mode with a hover-revealed model: connected ports never draw a visible glyph (the edge line is the only signal), and unconnected ports only appear — clustered near a sensible default direction, with a readable label — while the node is hovered or a connection drag is in progress anywhere on the canvas.

**Architecture:** All changes live in `ui/src/canvas/nodes/radialPortGeometry.ts` (new pure functions: clustering, label offset, two split style functions) and `ui/src/canvas/nodes/RadialNodePorts.tsx` (the one shared renderer both `AgentNode.tsx` and `LoopNode.tsx` already call — neither caller needs to change). React Flow `<Handle>` elements stay mounted at all times for every port (required so React Flow's internal edge-position and connection-drop-target bookkeeping never has to deal with handles appearing/disappearing); only their CSS `opacity`/`pointerEvents` and, for unconnected ports, their computed angle change based on reveal state.

**Tech Stack:** React, TypeScript, `@xyflow/react` v12 (`Handle`, `useConnection`, `ReactFlowProvider`), Zustand (`useUiStore`), Vitest, `@testing-library/react` + `@testing-library/jest-dom` (already configured globally via `ui/src/test/setup.ts`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-15-freeform-port-connector-design.md`.
- Scope is `ui/` only — no backend changes, no `Architecture`/`compile_graph` changes. This is a pure canvas view-layer redesign (same principle as the Loop Scope work).
- Connected ports (ports with a real partner edge) NEVER render a visible dot glyph, in any state — not in connection edit mode, not on hover. Their `<Handle>` stays at `opacity: 0, pointerEvents: 'none'` permanently. The edge line touching the node boundary is the only visual signal.
- Unconnected ports are visible+interactive only when `useUiStore.showConnectionPorts` is `true` AND (the node is locally hovered OR `useConnection((c) => c.inProgress)` is `true`). Outside that, they render nothing.
- `<Handle>` elements for every port (connected or not) are always mounted in the DOM — never conditionally mounted/unmounted based on reveal state. Only their inline style changes. (Reveal-gated port *labels*, by contrast, are fine to conditionally mount — they carry no React Flow registration.)
- `AgentNode.tsx` and `LoopNode.tsx` require zero changes — both already pass `RadialNodePortsProps` straight through, and both already wrap their call to `RadialNodePorts` in a `position: relative` container, which is all the new hover-tracking layer needs.
- `ui/src/canvas/loop/loopProjection.ts` and the `viewOverride` prop are unaffected — this plan only changes how ports are styled/positioned, not how loop-collapsed synthetic ports are computed.
- Run `cd ui && npm run test && npm run build` after every task — `npm run build` runs `tsc -b`, which catches type errors `npm run test` alone does not (see `CLAUDE.local.md`).

---

### Task 1: Pure geometry/style functions — clustering, label offset, style split

**Files:**
- Modify: `ui/src/canvas/nodes/radialPortGeometry.ts`
- Test: `ui/src/__tests__/radialNodePorts.test.ts`

**Interfaces:**
- Produces: `clusterFallbackAngles(count: number, anchorAngleDeg: number, spreadDeg?: number): number[]`, `unconnectedPortAngles(inputCount: number, outputCount: number, seamAngleDeg: number): { inputAngles: number[]; outputAngles: number[] }`, `labelPointFromAngleDeg(angleDeg: number, offset?: number): { left: number; top: number }`, `connectedHandleStyle(): { width: number; height: number; opacity: number; pointerEvents: 'none' }`, `revealableHandleStyle(color: string, revealed: boolean): { width: number; height: number; background: string; border: string; borderRadius: string; opacity: number; pointerEvents: 'auto' | 'none' }` — all consumed by Task 2/3's rewrite of `RadialNodePorts.tsx`.
- Leaves the existing `handleStyle` export in place, unused by nothing new yet — Task 2 removes it once `RadialNodePorts.tsx` stops calling it. (Removing it here would leave the still-unmodified `RadialNodePorts.tsx` importing a name that no longer exists, breaking `tsc -b` until Task 2 lands.)

- [ ] **Step 1: Write the failing tests**

Add to `ui/src/__tests__/radialNodePorts.test.ts` (append after the existing `resolveNodePortAngles` describe block; keep every existing block untouched):

```ts
import {
  angleDegBetween,
  clusterFallbackAngles,
  connectedHandleStyle,
  labelPointFromAngleDeg,
  pointFromAngleDeg,
  positionFromAngleDeg,
  resolveNodePortAngles,
  revealableHandleStyle,
  unconnectedPortAngles,
} from '@/canvas/nodes/radialPortGeometry'
```

(Replace the existing import block at the top of the file with the one above — it's the same four original names plus the five new ones, alphabetized.)

```ts
describe('clusterFallbackAngles', () => {
  it('returns an empty array for zero ports', () => {
    expect(clusterFallbackAngles(0, 90)).toEqual([])
  })

  it('places a single port exactly on the anchor angle', () => {
    expect(clusterFallbackAngles(1, 90)).toEqual([90])
  })

  it('spreads multiple ports symmetrically around the anchor at the given gap', () => {
    expect(clusterFallbackAngles(3, 0, 16)).toEqual([-16, 0, 16])
  })

  it('defaults to a 16 degree gap between adjacent ports', () => {
    const angles = clusterFallbackAngles(2, 0)
    expect(angles[1] - angles[0]).toBeCloseTo(16)
  })
})

describe('unconnectedPortAngles', () => {
  it('clusters inputs around the seam angle and outputs around its opposite', () => {
    const { inputAngles, outputAngles } = unconnectedPortAngles(1, 1, 40)
    expect(inputAngles).toEqual([40])
    expect(outputAngles).toEqual([220])
  })

  it('returns an empty array for a side with no unconnected ports', () => {
    const { inputAngles, outputAngles } = unconnectedPortAngles(0, 2, 0)
    expect(inputAngles).toEqual([])
    expect(outputAngles).toHaveLength(2)
  })
})

describe('labelPointFromAngleDeg', () => {
  it('sits further from the node center than the port dot at the same angle', () => {
    const dot = pointFromAngleDeg(30)
    const label = labelPointFromAngleDeg(30)
    const dotDist = Math.hypot(dot.left - 56, dot.top - 56)
    const labelDist = Math.hypot(label.left - 56, label.top - 56)
    expect(labelDist).toBeGreaterThan(dotDist)
  })

  it('defaults to a 22px outward offset along the same angle as pointFromAngleDeg', () => {
    const label = labelPointFromAngleDeg(0)
    expect(label.left).toBeCloseTo(56 + 56 + 22)
    expect(label.top).toBeCloseTo(56)
  })
})

describe('connectedHandleStyle', () => {
  it('is always invisible and non-interactive', () => {
    const style = connectedHandleStyle()
    expect(style.opacity).toBe(0)
    expect(style.pointerEvents).toBe('none')
  })
})

describe('revealableHandleStyle', () => {
  it('is visible and interactive when revealed', () => {
    const style = revealableHandleStyle('#fff', true)
    expect(style.opacity).toBe(1)
    expect(style.pointerEvents).toBe('auto')
  })

  it('is hidden and non-interactive when not revealed', () => {
    const style = revealableHandleStyle('#fff', false)
    expect(style.opacity).toBe(0)
    expect(style.pointerEvents).toBe('none')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && npx vitest run src/__tests__/radialNodePorts.test.ts`
Expected: FAIL — none of the five new names are exported from `@/canvas/nodes/radialPortGeometry` yet.

- [ ] **Step 3: Write the minimal implementation**

In `ui/src/canvas/nodes/radialPortGeometry.ts`, add after `pointFromAngleDeg` (keep `angleDegBetween`, `normalizeAngleDeg`, `positionFromAngleDeg`, `handleStyle`, `wrapIntoTurnFrom`, `resolveNodePortAngles` exactly as they are — nothing existing changes in this task):

```ts
/** Where a port's floating label sits — pushed further out from the node
 * boundary than the dot itself, along the same angle, so the two never
 * overlap. Only used for hover-revealed unconnected ports (RadialNodePorts.tsx). */
export function labelPointFromAngleDeg(angleDeg: number, offset = 22) {
  const radians = (angleDeg * Math.PI) / 180
  const distance = NODE_RADIUS + offset
  return {
    left: NODE_RADIUS + distance * Math.cos(radians),
    top: NODE_RADIUS - distance * Math.sin(radians),
  }
}

/**
 * Angles for `count` ports that have no real partner yet, clustered tightly
 * around `anchorAngleDeg` instead of scattered around the full circle. Used
 * only while these ports are hover-revealed for making a new connection —
 * see RadialNodePorts.tsx. `spreadDeg` is the angular gap between adjacent
 * ports in the cluster.
 */
export function clusterFallbackAngles(count: number, anchorAngleDeg: number, spreadDeg = 16): number[] {
  if (count === 0) return []
  const span = (count - 1) * spreadDeg
  return Array.from({ length: count }, (_, index) => anchorAngleDeg - span / 2 + index * spreadDeg)
}

/**
 * Where a node's *unconnected* ports cluster while hover-revealed: inputs
 * toward the hub-facing direction (`seamAngleDeg` — the same low-traffic
 * default `resolveNodePortAngles` already anchors its sort seam to), outputs
 * toward the opposite, rim-facing direction. Keeping the two groups on
 * opposite sides means they never overlap each other even when both are
 * revealed on the same node at once.
 */
export function unconnectedPortAngles(
  inputCount: number,
  outputCount: number,
  seamAngleDeg: number,
): { inputAngles: number[]; outputAngles: number[] } {
  return {
    inputAngles: clusterFallbackAngles(inputCount, seamAngleDeg),
    outputAngles: clusterFallbackAngles(outputCount, seamAngleDeg + 180),
  }
}

/** Style for an already-connected port's Handle. Purely functional — React
 * Flow still needs it mounted at its real position to compute the edge's
 * path — but it never becomes visible or interactive. The edge line itself
 * is the only signal that this connection exists (see spec §1). */
export function connectedHandleStyle() {
  return { width: 10, height: 10, opacity: 0, pointerEvents: 'none' } as const
}

/** Style for an unconnected port's Handle — a small dot, shown only while
 * `revealed` (the node is hovered, or a connection is in progress anywhere
 * on the canvas — see RadialNodePorts.tsx). */
export function revealableHandleStyle(color: string, revealed: boolean) {
  return {
    width: 10,
    height: 10,
    background: '#0e1511',
    border: `2px solid ${color}`,
    borderRadius: '50%',
    opacity: revealed ? 1 : 0,
    pointerEvents: revealed ? 'auto' : 'none',
  } as const
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && npx vitest run src/__tests__/radialNodePorts.test.ts`
Expected: PASS, both new and pre-existing tests.

- [ ] **Step 5: Typecheck and full suite**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/radialPortGeometry.ts ui/src/__tests__/radialNodePorts.test.ts
git commit -m "feat(ui): add port clustering, label offset, and split handle styles

Pure functions only — nothing calls them yet. clusterFallbackAngles/
unconnectedPortAngles replace the index-based 360-degree fallback with a
tight cluster near the node's hub/rim direction; connectedHandleStyle/
revealableHandleStyle split the always-opacity-toggled handleStyle into
'never visible' (connected) and 'visible only when revealed' (unconnected)."
```

---

### Task 2: `RadialNodePorts.tsx` — connected/unconnected split + local hover reveal

**Files:**
- Modify: `ui/src/canvas/nodes/radialPortGeometry.ts` (remove now-dead `handleStyle`)
- Modify: `ui/src/canvas/nodes/RadialNodePorts.tsx`
- Create: `ui/src/__tests__/radialNodePortsReveal.test.tsx`

**Interfaces:**
- Consumes: `clusterFallbackAngles`, `unconnectedPortAngles`, `connectedHandleStyle`, `revealableHandleStyle` from Task 1; `pointFromAngleDeg`, `positionFromAngleDeg`, `resolveNodePortAngles` (unchanged, existing).
- Produces: no new exports — `RadialNodePortsProps` (nodeId, inputs, outputs, color, viewOverride) is unchanged, so `AgentNode.tsx`/`LoopNode.tsx` need no edits.

- [ ] **Step 1: Remove the now-unused `handleStyle` from `radialPortGeometry.ts`**

Delete this block (it sits right after `angleDegBetween`/`normalizeAngleDeg`/`positionFromAngleDeg`, before `wrapIntoTurnFrom`):

```ts
/** Shared handle style for every port dot (real nodes and collapsed loop
 * scope containers alike) — hidden by default, revealed only in connection
 * edit mode (`useUiStore.showConnectionPorts`). */
export function handleStyle(color: string, visible: boolean) {
  return {
    width: 10,
    height: 10,
    background: '#0e1511',
    border: `2px solid ${color}`,
    borderRadius: '50%',
    opacity: visible ? 1 : 0,
    pointerEvents: visible ? 'auto' : 'none',
  } as const
}
```

- [ ] **Step 2: Write the failing test**

Create `ui/src/__tests__/radialNodePortsReveal.test.tsx`:

```tsx
import { beforeEach, describe, expect, it } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { RadialNodePorts } from '@/canvas/nodes/RadialNodePorts'

function renderPorts() {
  return render(
    <ReactFlowProvider>
      <RadialNodePorts
        nodeId="n1"
        inputs={[{ id: 'task', label: 'Task', dataType: 'text' }]}
        outputs={[{ id: 'plan', label: 'Plan', dataType: 'plan' }]}
      />
    </ReactFlowProvider>,
  )
}

describe('RadialNodePorts — local hover reveal', () => {
  beforeEach(() => {
    useGraphStore.setState({ nodes: [], edges: [], radialCenterId: null })
    useUiStore.setState({ showConnectionPorts: true })
  })

  it('hides unconnected port handles until the node is hovered', () => {
    const { container } = renderPorts()
    const input = container.querySelector('[aria-label="Input port: Task"]')!
    expect(input).toHaveStyle({ opacity: '0', pointerEvents: 'none' })
  })

  it('reveals unconnected port handles on hover, hides them again on leave', () => {
    const { container } = renderPorts()
    const hoverZone = container.querySelector('[aria-hidden="true"]')!

    fireEvent.mouseEnter(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '1',
      pointerEvents: 'auto',
    })

    fireEvent.mouseLeave(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '0',
      pointerEvents: 'none',
    })
  })

  it('never reveals when connection edit mode is off, even while hovered', () => {
    useUiStore.setState({ showConnectionPorts: false })
    const { container } = renderPorts()
    const hoverZone = container.querySelector('[aria-hidden="true"]')!

    fireEvent.mouseEnter(hoverZone)
    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({ opacity: '0' })
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: FAIL — the hover-zone element (`[aria-hidden="true"]`) doesn't exist yet, and unconnected ports are still always visible whenever `showConnectionPorts` is true (the old behavior).

- [ ] **Step 4: Replace `RadialNodePorts.tsx`**

Replace the full contents of `ui/src/canvas/nodes/RadialNodePorts.tsx`:

```tsx
import { Fragment, useState } from 'react'
import { Handle } from '@xyflow/react'
import type { Port } from '@/types'
import { useUiStore } from '@/stores/useUiStore'
import {
  connectedHandleStyle,
  pointFromAngleDeg,
  positionFromAngleDeg,
  resolveNodePortAngles,
  revealableHandleStyle,
  unconnectedPortAngles,
} from './radialPortGeometry'
import { computeHubRimAngles, useHubRimAngles, type HubRimAngles } from './hubRimAngles'

type PortSide = 'input' | 'output'
type SidedPort = Port & { side: PortSide }

type ViewOverride = {
  nodes: { id: string; position: { x: number; y: number } }[]
  edges: { source: string; sourceHandle?: string | null; target: string; targetHandle?: string | null }[]
  radialCenterId: string | null
}

type RadialNodePortsProps = {
  nodeId: string
  inputs: Port[]
  outputs: Port[]
  color?: string
  /** Bypasses the live graph-store subscription and computes partner angles
   * against this projected view instead. Used by the collapsed loop node,
   * whose ports are synthetic (rerouted crossing edges, see
   * `canvas/loop/loopProjection.ts`) and don't exist in the raw store's edge
   * list. Real canvas nodes omit this and read live from the store, exactly
   * as before this prop existed. */
  viewOverride?: ViewOverride
}

/**
 * Renders every port around the node's full 360-degree boundary. Connected
 * ports never draw a visible dot — the edge line already shows exactly
 * where they attach (see radialPortGeometry.ts's connectedHandleStyle).
 * Unconnected ports draw nothing until the node is hovered in connection
 * edit mode, at which point they appear clustered near a default direction
 * (inputs hub-facing, outputs rim-facing) instead of claiming a permanent
 * slot on the circle.
 */
export function RadialNodePorts({ nodeId, inputs, outputs, color = '#3c4a42', viewOverride }: RadialNodePortsProps) {
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const [isHovered, setIsHovered] = useState(false)
  const liveInputAngles = useHubRimAngles(nodeId, inputs, 'input')
  const liveOutputAngles = useHubRimAngles(nodeId, outputs, 'output')

  const inputAngles: HubRimAngles = viewOverride
    ? computeHubRimAngles({ nodeId, ports: inputs, side: 'input', ...viewOverride })
    : liveInputAngles
  const outputAngles: HubRimAngles = viewOverride
    ? computeHubRimAngles({ nodeId, ports: outputs, side: 'output', ...viewOverride })
    : liveOutputAngles

  const ports: SidedPort[] = [
    ...inputs.map((port) => ({ ...port, side: 'input' as const })),
    ...outputs.map((port) => ({ ...port, side: 'output' as const })),
  ]
  if (ports.length === 0) return null

  const partnerAngleDegByPortId = {
    ...inputAngles.partnerAngleDegByPortId,
    ...outputAngles.partnerAngleDegByPortId,
  }
  // rimAngleDeg doesn't depend on `side` or the port list — both calls above
  // always agree, so either is fine to use here.
  const seamAngleDeg = inputAngles.rimAngleDeg

  const connectedPorts = ports.filter((port) => partnerAngleDegByPortId[port.id] !== undefined)
  const unconnectedInputs = inputs.filter((port) => partnerAngleDegByPortId[port.id] === undefined)
  const unconnectedOutputs = outputs.filter((port) => partnerAngleDegByPortId[port.id] === undefined)

  const connectedAngles = resolveNodePortAngles(
    connectedPorts.map((port) => ({ partnerAngleDeg: partnerAngleDegByPortId[port.id] })),
    seamAngleDeg,
  )
  const { inputAngles: unconnectedInputAngles, outputAngles: unconnectedOutputAngles } = unconnectedPortAngles(
    unconnectedInputs.length,
    unconnectedOutputs.length,
    seamAngleDeg,
  )

  const revealed = showConnectionPorts && isHovered

  return (
    <>
      <div
        className="absolute inset-0 rounded-full"
        style={{ pointerEvents: 'auto' }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        aria-hidden="true"
      />
      {connectedPorts.map((port, index) => (
        <Handle
          key={`connected:${port.side}:${port.id}`}
          type={port.side === 'input' ? 'target' : 'source'}
          position={positionFromAngleDeg(connectedAngles[index])}
          id={port.id}
          style={{
            ...connectedHandleStyle(),
            ...pointFromAngleDeg(connectedAngles[index]),
            transform: 'translate(-50%, -50%)',
          }}
          title={`${port.side === 'input' ? 'Input' : 'Output'}: ${port.label}`}
          aria-label={`${port.side === 'input' ? 'Input' : 'Output'} port: ${port.label}`}
        />
      ))}
      {unconnectedInputs.map((port, index) => (
        <Handle
          key={`unconnected:input:${port.id}`}
          type="target"
          position={positionFromAngleDeg(unconnectedInputAngles[index])}
          id={port.id}
          style={{
            ...revealableHandleStyle(color, revealed),
            ...pointFromAngleDeg(unconnectedInputAngles[index]),
            transform: 'translate(-50%, -50%)',
          }}
          title={`Input: ${port.label}`}
          aria-label={`Input port: ${port.label}`}
        />
      ))}
      {unconnectedOutputs.map((port, index) => (
        <Handle
          key={`unconnected:output:${port.id}`}
          type="source"
          position={positionFromAngleDeg(unconnectedOutputAngles[index])}
          id={port.id}
          style={{
            ...revealableHandleStyle(color, revealed),
            ...pointFromAngleDeg(unconnectedOutputAngles[index]),
            transform: 'translate(-50%, -50%)',
          }}
          title={`Output: ${port.label}`}
          aria-label={`Output port: ${port.label}`}
        />
      ))}
    </>
  )
}
```

Note what changed structurally from before: the single combined `ports.map(...)` loop (which fed every port, connected or not, through one `resolveNodePortAngles` call plus an even-spacing fallback) is now three separate loops — connected ports still go through `resolveNodePortAngles` (unchanged math, now fed only the subset that actually has a partner), while unconnected input/output ports get their angles from Task 1's `unconnectedPortAngles` instead. The `Fragment` wrapper each `<Handle>` used to sit in is gone — Task 3 reintroduces per-port `Fragment`s once a second sibling (the label) needs to share a key.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: PASS, all three cases.

- [ ] **Step 6: Typecheck and full suite**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS. This also confirms `AgentNode.tsx`/`LoopNode.tsx` still compile unchanged against the same `RadialNodePortsProps`.

- [ ] **Step 7: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/radialPortGeometry.ts ui/src/canvas/nodes/RadialNodePorts.tsx ui/src/__tests__/radialNodePortsReveal.test.ts
git commit -m "feat(ui): hover-reveal unconnected ports, hide connected-port glyphs

Connected ports now render their Handle at opacity 0 permanently — the
edge line is the only visual signal a connection exists. Unconnected
ports render nothing until the node is hovered in connection edit mode,
at which point they appear clustered near the hub/rim direction instead
of scattered by index around the full circle."
```

---

### Task 3: Floating port labels for revealed ports

**Files:**
- Modify: `ui/src/canvas/nodes/RadialNodePorts.tsx`
- Modify: `ui/src/__tests__/radialNodePortsReveal.test.ts` → rename to `.tsx` already done in Task 2; extend it here.

**Interfaces:**
- Consumes: `labelPointFromAngleDeg` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `ui/src/__tests__/radialNodePortsReveal.test.tsx`, inside the existing `describe('RadialNodePorts — local hover reveal', ...)` block (after the last `it`):

```tsx
  it('shows the port label text only while revealed', () => {
    const { container, queryByText, getByText } = renderPorts()
    expect(queryByText('Task')).not.toBeInTheDocument()
    expect(queryByText('Plan')).not.toBeInTheDocument()

    const hoverZone = container.querySelector('[aria-hidden="true"]')!
    fireEvent.mouseEnter(hoverZone)
    expect(getByText('Task')).toBeInTheDocument()
    expect(getByText('Plan')).toBeInTheDocument()

    fireEvent.mouseLeave(hoverZone)
    expect(queryByText('Task')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: FAIL — no label text is rendered anywhere yet.

- [ ] **Step 3: Add labels to `RadialNodePorts.tsx`**

Add `labelPointFromAngleDeg` to the import from `./radialPortGeometry`:

```ts
import {
  connectedHandleStyle,
  labelPointFromAngleDeg,
  pointFromAngleDeg,
  positionFromAngleDeg,
  resolveNodePortAngles,
  revealableHandleStyle,
  unconnectedPortAngles,
} from './radialPortGeometry'
```

Replace the `unconnectedInputs.map(...)` block with:

```tsx
      {unconnectedInputs.map((port, index) => {
        const angle = unconnectedInputAngles[index]
        return (
          <Fragment key={`unconnected:input:${port.id}`}>
            <Handle
              type="target"
              position={positionFromAngleDeg(angle)}
              id={port.id}
              style={{
                ...revealableHandleStyle(color, revealed),
                ...pointFromAngleDeg(angle),
                transform: 'translate(-50%, -50%)',
              }}
              title={`Input: ${port.label}`}
              aria-label={`Input port: ${port.label}`}
            />
            {revealed && (
              <div
                className="pointer-events-none absolute whitespace-nowrap rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold text-[#dde4dd] shadow-sm"
                style={{ ...labelPointFromAngleDeg(angle), transform: 'translate(-50%, -50%)' }}
              >
                {port.label}
              </div>
            )}
          </Fragment>
        )
      })}
```

Replace the `unconnectedOutputs.map(...)` block with the same pattern:

```tsx
      {unconnectedOutputs.map((port, index) => {
        const angle = unconnectedOutputAngles[index]
        return (
          <Fragment key={`unconnected:output:${port.id}`}>
            <Handle
              type="source"
              position={positionFromAngleDeg(angle)}
              id={port.id}
              style={{
                ...revealableHandleStyle(color, revealed),
                ...pointFromAngleDeg(angle),
                transform: 'translate(-50%, -50%)',
              }}
              title={`Output: ${port.label}`}
              aria-label={`Output port: ${port.label}`}
            />
            {revealed && (
              <div
                className="pointer-events-none absolute whitespace-nowrap rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold text-[#dde4dd] shadow-sm"
                style={{ ...labelPointFromAngleDeg(angle), transform: 'translate(-50%, -50%)' }}
              >
                {port.label}
              </div>
            )}
          </Fragment>
        )
      })}
```

The `connectedPorts.map(...)` block is untouched — connected ports never get a label, matching that they never get a visible dot either.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: PASS, all four cases in the file.

- [ ] **Step 5: Typecheck and full suite**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/RadialNodePorts.tsx ui/src/__tests__/radialNodePortsReveal.test.tsx
git commit -m "feat(ui): show port label text next to revealed handles

Labels mount/unmount with reveal state directly (unlike Handles, they
carry no React Flow registration, so there's no reason to keep them
always-mounted) — positioned further out along the same angle as the
dot via labelPointFromAngleDeg, so the two never overlap."
```

---

### Task 4: Reveal during any in-progress connection drag (drop-target reachability)

**Files:**
- Modify: `ui/src/canvas/nodes/RadialNodePorts.tsx`
- Modify: `ui/src/__tests__/radialNodePortsReveal.test.tsx`

**Interfaces:**
- Consumes: `useConnection` from `@xyflow/react` (v12; returns `ConnectionState`, selector overload returns just the selected slice).

- [ ] **Step 1: Write the failing test**

Add near the top of `ui/src/__tests__/radialNodePortsReveal.test.tsx`, before the existing `describe` block (this mock applies file-wide but only overrides `useConnection` — every other export, including `ReactFlowProvider` and `Handle`, passes through untouched, so it doesn't affect the Task 2/3 tests already in this file):

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { ReactFlowProvider } from '@xyflow/react'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { RadialNodePorts } from '@/canvas/nodes/RadialNodePorts'

const connectionInProgress = vi.hoisted(() => ({ value: false }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useConnection: (selector: (c: { inProgress: boolean }) => unknown) =>
      selector({ inProgress: connectionInProgress.value }),
  }
})
```

(This replaces the file's existing top-of-file imports — `beforeEach`/`describe`/`expect`/`it` gain `vi`, and the three `@/...` imports plus `ReactFlowProvider` stay exactly as they were.)

Add a new `beforeEach` reset and a new `describe` block at the end of the file:

```tsx
describe('RadialNodePorts — reveal while another connection is in progress', () => {
  beforeEach(() => {
    useGraphStore.setState({ nodes: [], edges: [], radialCenterId: null })
    useUiStore.setState({ showConnectionPorts: true })
    connectionInProgress.value = false
  })

  it('reveals unconnected ports even without local hover, while a connection is in progress', () => {
    connectionInProgress.value = true
    const { container } = renderPorts()

    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({
      opacity: '1',
      pointerEvents: 'auto',
    })
  })

  it('stays hidden when no connection is in progress and the node is not hovered', () => {
    const { container } = renderPorts()

    expect(container.querySelector('[aria-label="Input port: Task"]')).toHaveStyle({ opacity: '0' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: FAIL on the first new case — nothing in `RadialNodePorts.tsx` reads `useConnection` yet, so `connectionInProgress.value = true` has no effect.

- [ ] **Step 3: Wire `useConnection` into `RadialNodePorts.tsx`**

Change the import line:

```ts
import { Handle, useConnection } from '@xyflow/react'
```

Add the subscription next to the existing `showConnectionPorts`/`isHovered` reads:

```ts
  const showConnectionPorts = useUiStore((s) => s.showConnectionPorts)
  const [isHovered, setIsHovered] = useState(false)
  const connectionInProgress = useConnection((c) => c.inProgress)
```

Change the `revealed` computation:

```ts
  const revealed = showConnectionPorts && (isHovered || connectionInProgress)
```

Everything else in the file is unchanged — `revealed` already flows into every place that needs it (`revealableHandleStyle(color, revealed)`, the `{revealed && (...)}` label blocks).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/radialNodePortsReveal.test.ts`
Expected: PASS, all six cases in the file (four from Tasks 2-3, two new here).

- [ ] **Step 5: Typecheck and full suite**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 6: Manual visual verification**

This sandbox has no working headless-browser setup (`CLAUDE.local.md`), so this step is done by the user:

```bash
./start.sh
```

Open the frontend, switch to Agent mode, turn on "연결 편집모드", and confirm:
- Nodes show no port dots at all until you hover them; unconnected ports then appear clustered to one side with readable labels, not scattered around the whole circle.
- Already-connected ports never show a dot, hovered or not — only the edge line touching the boundary.
- Starting a drag from one node's revealed port label, then moving toward a different node, reveals that other node's open ports too (not just the one you started on) so you can actually drop onto it.
- Turning "연결 편집모드" off hides everything again, even mid-hover.

- [ ] **Step 7: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/nodes/RadialNodePorts.tsx ui/src/__tests__/radialNodePortsReveal.test.tsx
git commit -m "feat(ui): reveal every node's open ports during an active connection drag

React Flow determines valid drop targets during a connection drag via
DOM hit-testing, which skips pointer-events:none elements — so a target
node's ports need pointer-events restored as soon as any drag starts,
not only once the cursor's own mouseenter fires on that node (which
native pointer capture during the drag can suppress)."
```

---

## Self-Review Notes

- **Spec coverage**: §1 (connected ports never show a glyph) → Task 2's `connectedHandleStyle`. §2 (hover-revealed, clustered, labeled unconnected ports) → Tasks 2-3. §3 (pointer-events during an active drag) → Task 4. Non-goals (edge routing, data model, loop projection, classic mode) are untouched by every task — no task modifies `AgentEdge.tsx`, `loopProjection.ts`, `useGraphStore.ts`, or any backend file.
- **Placeholder scan**: none — every step has complete, runnable code and exact file contents.
- **Type consistency**: `unconnectedPortAngles`'s return shape (`{ inputAngles, outputAngles }`) is destructured identically in Task 2's `RadialNodePorts.tsx` rewrite. `revealed: boolean` is threaded unchanged from Task 2 through Task 3 (label conditional) and Task 4 (its computation gains `|| connectionInProgress`) — no task renames it. `connectedHandleStyle()`/`revealableHandleStyle(color, revealed)` signatures match their Task 1 definitions exactly at every call site.
- **Task ordering hazard avoided**: Task 1 deliberately leaves the old `handleStyle` export in place (unused) so the codebase still typechecks between Task 1 and Task 2 — `RadialNodePorts.tsx` (unmodified until Task 2) still imports it. Task 2 removes `handleStyle` in the same commit that stops using it.
