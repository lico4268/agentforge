import type { NodeManifest } from '@/types'

/**
 * Bundled fallback node set — used when the backend /api/nodes is unreachable.
 * Mirrors server/manifests.py exactly: type ids, runtime, port ids, config keys.
 * node-spec.md §4 가 이 목록의 정의 문서다.
 */
export const BUILTIN_MANIFESTS: NodeManifest[] = [

  // ── I/O ────────────────────────────────────────────────────────────────────

  {
    type: 'io.input',
    runtime: 'io',
    category: 'io',
    label: 'Input',
    description: '그래프 진입점. task와 tag를 시드.',
    inputs: [],
    outputs: [
      { id: 'task', label: 'Task', dataType: 'text' },
      { id: 'tags', label: 'Tags', dataType: 'any' },
    ],
    config: [
      {
        key: 'sample',
        label: 'Sample task',
        type: 'text',
        placeholder: 'e.g. Natalia sold clips to 48 of her friends…',
      },
      { key: 'taskTags', label: 'Task tags', type: 'string[]' },
    ],
  },

  {
    type: 'io.output',
    runtime: 'io',
    category: 'io',
    label: 'Output',
    description: '그래프 종단.',
    inputs: [{ id: 'result', label: 'Result', dataType: 'any', required: true }],
    outputs: [],
    config: [],
  },

  // ── Model ──────────────────────────────────────────────────────────────────

  {
    type: 'model.binding',
    runtime: 'model',
    category: 'model',
    label: 'Model',
    description: '공유 LLM 부품. llm_step의 model 포트에 연결하면 인라인 설정을 덮어씀.',
    inputs: [],
    outputs: [{ id: 'model', label: 'Model', dataType: 'model' }],
    config: [
      {
        key: 'provider',
        label: 'Provider',
        type: 'select',
        default: 'google',
        options: [
          { label: 'Anthropic', value: 'anthropic' },
          { label: 'OpenAI',    value: 'openai'    },
          { label: 'Google',    value: 'google'    },
          { label: 'Local',     value: 'local'     },
        ],
      },
      {
        key: 'model',
        label: 'Model ID',
        type: 'model-id',
        default: 'gemini-3.5-flash',
        description: 'provider 선택에 따라 목록이 필터링됩니다.',
      },
      { key: 'temperature', label: 'Temperature', type: 'number', default: 0 },
    ],
  },

  // ── Cognitive (llm_step 프리셋) ────────────────────────────────────────────

  {
    type: 'planning.decompose',
    runtime: 'llm_step',
    category: 'cognitive',
    label: 'Planning',
    description: 'task를 정렬된 단계(plan)로 분해.',
    inputs: [
      { id: 'task',  label: 'Task',  dataType: 'text',  required: true  },
      { id: 'model', label: 'Model', dataType: 'model', required: false },
    ],
    outputs: [{ id: 'plan', label: 'Plan', dataType: 'plan' }],
    config: [
      {
        key: 'strategy',
        label: 'Strategy',
        type: 'select',
        default: 'decompose',
        options: [
          { label: 'Decompose',  value: 'decompose'  },
          { label: 'Goal-first', value: 'goal'       },
          { label: 'Multi-step', value: 'multistep'  },
        ],
      },
    ],
    defaults: {
      systemPrompt: 'Decompose the task into ordered steps and return as JSON.',
      outputSchema: { steps: 'string[]' },
    },
  },

  {
    type: 'reasoning.cot',
    runtime: 'llm_step',
    category: 'cognitive',
    label: 'Reasoning',
    description: 'Chain-of-thought 추론. answer와 confidence를 반환.',
    inputs: [
      { id: 'task',  label: 'Task',  dataType: 'text',  required: true  },
      { id: 'plan',  label: 'Plan',  dataType: 'plan',  required: false },
      { id: 'model', label: 'Model', dataType: 'model', required: false },
    ],
    outputs: [
      { id: 'answer',     label: 'Answer',     dataType: 'text'   },
      { id: 'confidence', label: 'Confidence', dataType: 'number' },
    ],
    config: [
      {
        key: 'style',
        label: 'Style',
        type: 'select',
        default: 'chain_of_thought',
        options: [
          { label: 'Chain of thought', value: 'chain_of_thought' },
          { label: 'Direct',           value: 'direct'           },
        ],
      },
    ],
    defaults: {
      systemPrompt: 'Solve the task step by step. Return your answer and confidence (0-1).',
      outputSchema: { answer: 'string', confidence: 'number' },
    },
  },

  // ── Policy ─────────────────────────────────────────────────────────────────

  {
    type: 'review.intent',
    runtime: 'review',
    category: 'policy',
    label: 'Review',
    description: '의도×기준 대조 리뷰. ReviewDelta 기반 accept / refine / clarify 3분기.',
    maxModelSlots: 2,
    inputs: [
      { id: 'answer', label: 'Answer', dataType: 'text', required: true  },
      { id: 'task',   label: 'Task',   dataType: 'text', required: false },
    ],
    outputs: [
      { id: 'accept',  label: 'Accept',  dataType: 'any' },
      { id: 'refine',  label: 'Refine',  dataType: 'any' },
      { id: 'clarify', label: 'Clarify', dataType: 'any' },
    ],
    config: [
      {
        key: 'criteria',
        label: 'Acceptance criteria',
        type: 'string[]',
        placeholder: '단위(원) 포함…',
        description: '이진 판정 가능한 합격 기준 목록. 비면 의도 정합성만 평가.',
      },
      { key: 'maxRetries', label: 'Max retries', type: 'number', default: 2 },
      {
        key: 'escalateTags',
        label: 'Escalate tags',
        type: 'string[]',
        description: '이 태그가 있으면 자동 통과(accept) 금지 → clarify.',
      },
    ],
    defaults: {
      outputSchema: {
        per_criterion: 'object[]',
        misalignments: 'string[]',
        elicit_questions: 'string[]',
        proposed_criteria: 'string[]',
        reroute_hint: 'string',
      },
    },
  },

  // ── Human ──────────────────────────────────────────────────────────────────

  {
    type: 'human.checkpoint',
    runtime: 'checkpoint',
    category: 'human',
    label: 'Human Checkpoint',
    description: '실행 정지 후 인간 검토·수정·재실행. approve / revise / reject 3분기.',
    inputs: [{ id: 'review', label: 'Review', dataType: 'any' }],
    outputs: [
      { id: 'approve', label: 'Approve', dataType: 'any' },
      { id: 'revise',  label: 'Revise',  dataType: 'any' },
      { id: 'reject',  label: 'Reject',  dataType: 'any' },
    ],
    config: [
      {
        key: 'summarize',
        label: 'Summarize',
        type: 'select',
        default: 'off',
        options: [
          { label: 'Off',    value: 'off'    },
          { label: 'Fields', value: 'fields' },
          { label: 'LLM',    value: 'llm'    },
        ],
      },
      {
        key: 'blockUntil',
        label: 'Block until',
        type: 'select',
        default: 'always',
        options: [
          { label: 'Always',      value: 'always'      },
          { label: 'When flagged', value: 'when-flagged' },
        ],
      },
    ],
  },
]
