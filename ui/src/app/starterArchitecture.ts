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
    { id: 'input',             type: 'io.input',           position: { x: 300, y: 0   }, config: { sample: 'Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?' } },
    { id: 'planning',          type: 'planning.decompose',  position: { x: 300, y: 180 }, config: {} },
    { id: 'reasoning',         type: 'reasoning.cot',       position: { x: 300, y: 360 }, config: {} },
    { id: 'review_policy',     type: 'policy.review',       position: { x: 300, y: 540 }, config: { passThreshold: 0.85, autoThreshold: 0.6 } },
    { id: 'auto_verify',       type: 'verification.auto',   position: { x: 0,   y: 740 }, config: { maxRetries: 2 } },
    { id: 'human_checkpoint',  type: 'human.checkpoint',    position: { x: 600, y: 740 }, config: {} },
    { id: 'output',            type: 'io.output',           position: { x: 300, y: 940 }, config: {} },
  ],
  edges: [
    { id: 'e1', source: 'input',         sourceHandle: 'task',       target: 'planning',         targetHandle: 'task'       },
    { id: 'e2', source: 'planning',      sourceHandle: 'plan',       target: 'reasoning',        targetHandle: 'plan'       },
    { id: 'e3', source: 'input',         sourceHandle: 'task',       target: 'reasoning',        targetHandle: 'task'       },
    { id: 'e4', source: 'reasoning',     sourceHandle: 'answer',     target: 'review_policy',    targetHandle: 'answer'     },
    { id: 'e5', source: 'reasoning',     sourceHandle: 'confidence', target: 'review_policy',    targetHandle: 'confidence' },
    { id: 'e6', source: 'review_policy', sourceHandle: 'pass',       target: 'output',           targetHandle: 'result'     },
    { id: 'e7', source: 'review_policy', sourceHandle: 'auto',       target: 'auto_verify',      targetHandle: 'answer'     },
    { id: 'e8', source: 'review_policy', sourceHandle: 'human',      target: 'human_checkpoint', targetHandle: 'review'     },
    { id: 'e9', source: 'auto_verify',   sourceHandle: 'verdict',    target: 'output',           targetHandle: 'result'     },
    { id: 'e10', source: 'human_checkpoint', sourceHandle: 'approve', target: 'output',          targetHandle: 'result'     },
  ],
}
