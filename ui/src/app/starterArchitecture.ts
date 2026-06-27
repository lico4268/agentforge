import type { Architecture } from '@/types'

/**
 * Starter graph: Cognitive Core wired for top-to-bottom flow.
 * Input → Planning → Model → Verification Policy → (verify) Verification → Output
 *                                                 → (pass) Output
 *
 * Node spacing: ~180px vertical, branches split at x=0 / x=420.
 */
export const STARTER_ARCHITECTURE: Architecture = {
  version: '0.1',
  metadata: {
    name: 'Cognitive Core (starter)',
    description: 'Planning + conditional verification over a single model.',
    createdAt: new Date().toISOString(),
  },
  nodes: [
    { id: 'input',  type: 'io.input',                   position: { x: 200, y: 0   }, config: {} },
    { id: 'plan',   type: 'planning.task_decomposition', position: { x: 200, y: 180 }, config: {} },
    { id: 'model',  type: 'model.inference',             position: { x: 200, y: 360 }, config: {} },
    { id: 'policy', type: 'policy.verification',         position: { x: 200, y: 540 }, config: {} },
    { id: 'verify', type: 'verification.critique',       position: { x: 0,   y: 740 }, config: {} },
    { id: 'output', type: 'io.output',                   position: { x: 420, y: 740 }, config: {} },
  ],
  edges: [
    { id: 'e1', source: 'input',  sourceHandle: 'out',    target: 'plan',   targetHandle: 'in'  },
    { id: 'e2', source: 'plan',   sourceHandle: 'plan',   target: 'model',  targetHandle: 'in'  },
    { id: 'e3', source: 'model',  sourceHandle: 'out',    target: 'policy', targetHandle: 'in'  },
    { id: 'e4', source: 'policy', sourceHandle: 'verify', target: 'verify', targetHandle: 'in'  },
    { id: 'e5', source: 'policy', sourceHandle: 'pass',   target: 'output', targetHandle: 'in'  },
    { id: 'e6', source: 'verify', sourceHandle: 'pass',   target: 'output', targetHandle: 'in'  },
  ],
}
