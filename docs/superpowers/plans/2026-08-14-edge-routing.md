> 📄 **완료된 작업 기록** — 당시 구현 계획서다. 현재 설계 문서가 아니며, 현재 방향은 [DIRECTION.md](../../../DIRECTION.md) 참고.

# Edge Routing — Straight Forward Edges, Curved Loop-Back Only — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every forward edge on the agent canvas a straight line (boundary-to-boundary) and reserve curves for `loop.guard`'s re-entry edge only, fixing the visible kink caused by React Flow's 4-direction bezier tangent quantization.

**Architecture:** `AgentEdge.tsx` picks `getStraightPath` or `getBezierPath` per-edge based on a new structural check (`sourceHandle === 'loopBack'`) instead of the old screen-position heuristic (`sourceY > targetY`). No change to port placement (`radialPortGeometry.ts`) — the fix lives entirely in which path function consumes the already-correct continuous port coordinates.

**Tech Stack:** React, TypeScript, `@xyflow/react` (`getStraightPath`, `getBezierPath`), Vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-14-ui-canvas-design-philosophy-design.md` §2.
- Scope is `ui/` only — no backend changes, no `compile_graph` changes.
- Only `canvasNodeMode === 'agent'` renders edges through `AgentEdge` (`Canvas.tsx:94-98`); classic mode is untouched by this plan (out of scope per the spec's 비목표).
- Run `cd ui && npm run test` and `npm run build` (which runs `tsc -b`) after every task — per `CLAUDE.local.md`, `tsc -b` catches type errors `npm run test` does not.

---

### Task 1: `isLoopBackEdge` — structural loop-back detection

**Files:**
- Modify: `ui/src/canvas/edges/edgePresentation.ts`
- Test: `ui/src/__tests__/edgePresentation.test.ts`

**Interfaces:**
- Produces: `isLoopBackEdge(sourceHandle?: string | null): boolean` — imported by `AgentEdge.tsx` in Task 2.

- [ ] **Step 1: Write the failing test**

Add to `ui/src/__tests__/edgePresentation.test.ts` (keep the existing `describe('edgePresentation', ...)` block untouched, add a new one):

```ts
import { describe, expect, it } from 'vitest'
import { edgePresentation, isLoopBackEdge } from '@/canvas/edges/edgePresentation'

describe('isLoopBackEdge', () => {
  it('flags the loop.guard re-entry handle', () => {
    expect(isLoopBackEdge('loopBack')).toBe(true)
  })

  it('does not flag the loop.guard exit handle or any other handle', () => {
    expect(isLoopBackEdge('exit')).toBe(false)
    expect(isLoopBackEdge('accept')).toBe(false)
    expect(isLoopBackEdge(undefined)).toBe(false)
    expect(isLoopBackEdge(null)).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ui && npx vitest run src/__tests__/edgePresentation.test.ts`
Expected: FAIL — `isLoopBackEdge` is not exported from `@/canvas/edges/edgePresentation`.

- [ ] **Step 3: Write minimal implementation**

In `ui/src/canvas/edges/edgePresentation.ts`, add below the existing `CONDITIONAL_HANDLES` line:

```ts
const LOOP_BACK_HANDLE = 'loopBack'

/**
 * True when this edge is `loop.guard`'s re-entry edge — the one structural
 * signal every compiled graph guarantees for a cycle (an ungated cycle is a
 * compile error, see docs/superpowers/specs/2026-08-07-loop-node-design.md
 * §4), so no screen-position heuristic is needed to find it.
 */
export function isLoopBackEdge(sourceHandle?: string | null): boolean {
  return sourceHandle === LOOP_BACK_HANDLE
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ui && npx vitest run src/__tests__/edgePresentation.test.ts`
Expected: PASS, both new tests and the pre-existing `edgePresentation` tests.

- [ ] **Step 5: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/canvas/edges/edgePresentation.ts ui/src/__tests__/edgePresentation.test.ts
git commit -m "feat(ui): add isLoopBackEdge structural loop-back detection"
```

---

### Task 2: Straight forward edges, curved+dashed loop-back edges

**Files:**
- Modify: `ui/src/lib/categoryStyle.ts`
- Modify: `ui/src/canvas/edges/AgentEdge.tsx`

**Interfaces:**
- Consumes: `isLoopBackEdge(sourceHandle)` from Task 1; `edgePresentation(sourceHandle)` (existing, unchanged).
- Produces: `LOOP_ACCENT_COLOR` (exported `string` constant) — later reused by the loop-drill-down plan for the collapsed loop node's ripple halo, so this task is a dependency for that plan (sequencing note, not a blocking coupling — that plan can define its own copy if run first, but should prefer importing this one).

- [ ] **Step 1: Add the shared loop-purple constant**

In `ui/src/lib/categoryStyle.ts`, add after the `CATEGORY_META` block:

```ts
/** Loop-purple — reserved for loop-related UI (re-entry edges, the collapsed
 * loop node's ripple halo). Never mixed with a category color. */
export const LOOP_ACCENT_COLOR = '#a78bfa'
```

- [ ] **Step 2: Rewrite `AgentEdge.tsx` to branch on `isLoopBackEdge`**

Replace the full contents of `ui/src/canvas/edges/AgentEdge.tsx`:

```tsx
import { useState } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react'
import { edgePresentation, isLoopBackEdge } from './edgePresentation'
import { LOOP_ACCENT_COLOR } from '@/lib/categoryStyle'

export function AgentEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  sourceHandleId,
  markerEnd,
  selected,
}: EdgeProps) {
  const [isHovered, setIsHovered] = useState(false)
  const { conditional, color } = edgePresentation(sourceHandleId)
  const isLoopBack = isLoopBackEdge(sourceHandleId)

  // Forward edges: straight boundary-to-boundary. The port dot already sits
  // at its true continuous angle (radialPortGeometry.ts); a straight line
  // needs no tangent direction at all, so it can't be thrown off by the
  // 4-direction Position quantization getBezierPath relies on.
  // Loop-back edges: kept curved on purpose, so the return relationship
  // reads as visually distinct from the forward flow.
  const [edgePath, labelX, labelY] = isLoopBack
    ? getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
        curvature: 0.42,
      })
    : getStraightPath({ sourceX, sourceY, targetX, targetY })

  const showLabel = conditional || selected || isHovered
  const stroke = selected ? '#dde4dd' : isLoopBack ? LOOP_ACCENT_COLOR : color
  const arrowMarkerId = `agent-arrow-${id}`

  return (
    <>
      <defs>
        <marker
          id={arrowMarkerId}
          markerWidth="10"
          markerHeight="10"
          refX="8"
          refY="5"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={stroke} />
        </marker>
      </defs>
      <g onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
        <BaseEdge
          id={id}
          path={edgePath}
          markerEnd={markerEnd ?? `url(#${arrowMarkerId})`}
          interactionWidth={24}
          style={{
            stroke,
            strokeWidth: selected ? 2.5 : conditional ? 2 : 1.5,
            strokeDasharray: isLoopBack ? '6 4' : undefined,
          }}
        />
      </g>
      {showLabel && sourceHandleId && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute rounded-full border border-[#3c4a42] bg-[#161d19] px-1.5 py-0.5 font-mono text-[9px] font-semibold shadow-sm"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              color: stroke,
            }}
          >
            {sourceHandleId}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}
```

Note what was deleted: the `isFeedbackLoop = sourceY > targetY` screen-position heuristic and its use as `curvature: isFeedbackLoop ? 0.42 : 0.24` for every edge. Every non-loop-back edge now takes the straight-path branch unconditionally.

- [ ] **Step 3: Typecheck and run the full test suite**

Run: `cd ui && npm run test && npm run build`
Expected: both PASS. `npm run build` runs `tsc -b`, which is the check that catches `EdgeProps`/import errors `vitest` alone would miss.

- [ ] **Step 4: Manual visual verification**

This project has no working headless-browser setup in this sandbox (see `CLAUDE.local.md`), so this step is done by the user, not the agent:

```bash
./start.sh
```

Open the frontend, load the starter graph (`gsm8k-treatment` / `current canvas`), and confirm:
- All edges except `loop_guard`'s `loopBack → reasoning` edge are straight lines that meet each node's border exactly at the port dot's real position (no kink).
- The `loopBack` edge is curved, dashed, and loop-purple (`#a78bfa`), visually distinct from every other edge.
- Hover/selection behavior (label popup, thicker stroke) is unchanged from before.

- [ ] **Step 5: Commit**

```bash
cd /home/licodev/projects/agentforge
git add ui/src/lib/categoryStyle.ts ui/src/canvas/edges/AgentEdge.tsx
git commit -m "feat(ui): straight forward edges, curved+dashed loop-back edges

Replaces the sourceY>targetY screen-position heuristic with a structural
check (sourceHandle === 'loopBack') and switches forward edges from
getBezierPath to getStraightPath, eliminating the visible kink caused by
quantizing the port's continuous angle down to 4 Position buckets for the
bezier tangent."
```

---

## Self-Review Notes

- **Spec coverage**: implements spec §2 in full (straight forward edges, loop-back-only curve, dashed + loop-purple styling, port-dot-hidden-by-default behavior left untouched since nothing in this plan touches `RadialNodePorts.tsx`/`radialPortGeometry.ts`).
- **Placeholder scan**: none — every step has real, complete code.
- **Type consistency**: `isLoopBackEdge` signature (`(sourceHandle?: string | null) => boolean`) matches its one call site in `AgentEdge.tsx` exactly; `LOOP_ACCENT_COLOR` is a plain `string` export, matches its one usage as a CSS color value.
