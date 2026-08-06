import type { Architecture } from '@/types'

/**
 * 스타터 그래프: 의도 정합성 리뷰 흐름 (POLICY_REDESIGN.md Phase 1).
 * Input → Planning → Reasoning → Review (intent×criteria diff)
 *   ├ accept  → Output
 *   ├ refine  → Reasoning (재작업)
 *   └ clarify → Human Checkpoint → Output / Reasoning
 */
export const STARTER_ARCHITECTURE: Architecture = {
  version: '0.1',
  metadata: {
    name: 'GSM8K Treatment (starter)',
    description: 'Planning + Reasoning + 의도 정합성 Review 3분기 (accept / refine / clarify).',
    createdAt: new Date().toISOString(),
  },
  nodes: [
    { id: 'input',             type: 'io.input',           position: { x: 96,  y: 88  }, config: { sample: 'Natalia sold clips to 48 of her friends in April, and then she sold half as many clips in May. How many clips did Natalia sell altogether in April and May?' } },
    { id: 'planning',          type: 'planning.decompose',  position: { x: 272, y: 220 }, config: { modelSlots: [{ id: 'slot-planning', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'reasoning',         type: 'reasoning.cot',       position: { x: 472, y: 356 }, config: { modelSlots: [{ id: 'slot-reasoning', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'review',            type: 'review.intent',       position: { x: 690, y: 300 }, config: { criteria: [], maxRetries: 2, modelSlots: [{ id: 'slot-review', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'human_checkpoint',  type: 'human.checkpoint',    position: { x: 748, y: 520 }, config: {} },
    { id: 'output',            type: 'io.output',           position: { x: 522, y: 616 }, config: {} },
  ],
  edges: [
    { id: 'e1', source: 'input',            sourceHandle: 'task',    target: 'planning',         targetHandle: 'task'   },
    { id: 'e2', source: 'planning',         sourceHandle: 'plan',    target: 'reasoning',        targetHandle: 'plan'   },
    { id: 'e3', source: 'input',            sourceHandle: 'task',    target: 'reasoning',        targetHandle: 'task'   },
    { id: 'e4', source: 'reasoning',        sourceHandle: 'answer',  target: 'review',           targetHandle: 'answer' },
    { id: 'e5', source: 'review',           sourceHandle: 'accept',  target: 'output',           targetHandle: 'result' },
    { id: 'e6', source: 'review',           sourceHandle: 'refine',  target: 'reasoning',        targetHandle: 'task'   },
    { id: 'e7', source: 'review',           sourceHandle: 'clarify', target: 'human_checkpoint', targetHandle: 'review' },
    { id: 'e8', source: 'human_checkpoint', sourceHandle: 'approve', target: 'output',           targetHandle: 'result' },
  ],
  loopPolicies: [],
}
