import type { Architecture } from '@/types'

/**
 * 스타터 그래프: 의도 정합성 리뷰 흐름 (POLICY_REDESIGN.md Phase 1).
 * Input → Planning → Reasoning → Review (intent×criteria diff)
 *   ├ accept  → Output
 *   ├ refine  → Loop (loop.guard) ─ loop back → Reasoning (재작업)
 *   │                             └ exit      → Output (가드 소진 시)
 *   └ clarify → Human Checkpoint → Output
 *
 * refine 피드백이 Loop 노드를 거치는 것은 선택이 아니다 — 가드 없이 그려진 cycle은
 * compile_graph가 ValueError로 거부한다.
 * See docs/superpowers/specs/2026-08-07-loop-node-design.md §4.
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
    { id: 'loop_reentry',      type: 'loop.reentry',        position: { x: 328, y: 380 }, config: {} },
    { id: 'reasoning',         type: 'reasoning.cot',       position: { x: 472, y: 380 }, config: { modelSlots: [{ id: 'slot-reasoning', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'review',            type: 'review.intent',       position: { x: 690, y: 380 }, config: { criteria: [], maxRetries: 2, modelSlots: [{ id: 'slot-review', provider: 'google', model: 'gemini-3.1-flash-lite', temperature: 0, role: '' }] } },
    { id: 'loop_guard',        type: 'loop.guard',          position: { x: 916, y: 380 }, config: { kind: 'critiqueRevise', maxIterations: 3, onExhaustion: 'exit' } },
    { id: 'human_checkpoint',  type: 'human.checkpoint',    position: { x: 748, y: 520 }, config: {} },
    { id: 'output',            type: 'io.output',           position: { x: 522, y: 616 }, config: {} },
  ],
  edges: [
    { id: 'e1', source: 'input',            sourceHandle: 'task',    target: 'planning',         targetHandle: 'task'   },
    { id: 'e2', source: 'planning',         sourceHandle: 'plan',    target: 'reasoning',        targetHandle: 'plan'   },
    { id: 'e3', source: 'input',            sourceHandle: 'task',    target: 'reasoning',        targetHandle: 'task'   },
    { id: 'e4', source: 'reasoning',        sourceHandle: 'answer',  target: 'review',           targetHandle: 'answer' },
    { id: 'e5', source: 'review',           sourceHandle: 'accept',  target: 'output',           targetHandle: 'result' },
    { id: 'e6', source: 'review',           sourceHandle: 'refine',  target: 'loop_guard',       targetHandle: 'in'     },
    { id: 'e7', source: 'review',           sourceHandle: 'clarify', target: 'human_checkpoint', targetHandle: 'review' },
    { id: 'e8', source: 'human_checkpoint', sourceHandle: 'approve', target: 'output',           targetHandle: 'result' },
    { id: 'e9', source: 'loop_guard',       sourceHandle: 'loopBack', target: 'loop_reentry',     targetHandle: 'in'     },
    { id: 'e10', source: 'loop_guard',      sourceHandle: 'exit',     target: 'output',           targetHandle: 'result' },
    { id: 'e11', source: 'loop_reentry',    sourceHandle: 'out',      target: 'reasoning',        targetHandle: 'task'   },
  ],
}
