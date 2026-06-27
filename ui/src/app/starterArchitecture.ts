import type { Architecture } from '@/types'

/**
 * 스타터 그래프: node-spec.md §7 GSM8K Treatment 흐름.
 * Input → Planning → Reasoning → Review Policy
 *   ├ pass  → Output
 *   ├ auto  → Auto-Verify → Output
 *   └ human → Human Checkpoint → Output / Reasoning
 */
export const STARTER_ARCHITECTURE: Architecture = {
  version: '0.1',
  metadata: {
    name: 'GSM8K Treatment (starter)',
    description: 'Planning + Reasoning + Policy 3분기 (Auto-Verify / Human Checkpoint).',
    createdAt: new Date().toISOString(),
  },
  nodes: [
    { id: 'input',    type: 'io.input',           position: { x: 300, y: 0   }, config: { sample: 'Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?' } },
    { id: 'plan',     type: 'planning.decompose',  position: { x: 300, y: 180 }, config: {} },
    { id: 'reason',   type: 'reasoning.cot',       position: { x: 300, y: 360 }, config: {} },
    { id: 'policy',   type: 'policy.review',       position: { x: 300, y: 540 }, config: { passThreshold: 0.85, autoThreshold: 0.6 } },
    { id: 'verify',   type: 'verification.auto',   position: { x: 0,   y: 740 }, config: { maxRetries: 2 } },
    { id: 'human',    type: 'human.checkpoint',    position: { x: 600, y: 740 }, config: {} },
    { id: 'output',   type: 'io.output',           position: { x: 300, y: 940 }, config: {} },
  ],
  edges: [
    { id: 'e1', source: 'input',  sourceHandle: 'task',     target: 'plan',   targetHandle: 'task'     },
    { id: 'e2', source: 'plan',   sourceHandle: 'plan',     target: 'reason', targetHandle: 'plan'     },
    { id: 'e3', source: 'input',  sourceHandle: 'task',     target: 'reason', targetHandle: 'task'     },
    { id: 'e4', source: 'reason', sourceHandle: 'answer',   target: 'policy', targetHandle: 'answer'   },
    { id: 'e5', source: 'reason', sourceHandle: 'confidence', target: 'policy', targetHandle: 'confidence' },
    { id: 'e6', source: 'policy', sourceHandle: 'pass',     target: 'output', targetHandle: 'result'   },
    { id: 'e7', source: 'policy', sourceHandle: 'auto',     target: 'verify', targetHandle: 'answer'   },
    { id: 'e8', source: 'policy', sourceHandle: 'human',    target: 'human',  targetHandle: 'review'   },
    { id: 'e9', source: 'verify', sourceHandle: 'verdict',  target: 'output', targetHandle: 'result'   },
    { id: 'e10', source: 'human', sourceHandle: 'approve',  target: 'output', targetHandle: 'result'   },
  ],
}
