import type { NodeManifest } from '@/types'

/**
 * Bundled fallback node set — used when the backend /api/nodes is unreachable.
 * Mirrors backend/nodes/builtin/* exactly: type ids, port ids, config keys.
 * Adding a node = adding an entry here AND the corresponding NodeBase subclass.
 */
export const BUILTIN_MANIFESTS: NodeManifest[] = [

  // ── I/O ────────────────────────────────────────────────────────────────────

  {
    type: 'io.input',
    category: 'io',
    label: 'Input',
    description: 'Entry point — the question or task given to the agent.',
    inputs: [],
    outputs: [{ id: 'out', label: 'task', dataType: 'text', required: false }],
    config: [
      {
        key: 'sample',
        label: 'Sample task',
        type: 'text',
        placeholder: 'e.g. Natalia sold clips to 48 of her friends…',
        description: 'Used as the agent input when running in MockTransport or via direct API.',
      },
    ],
  },

  {
    type: 'io.output',
    category: 'io',
    label: 'Output',
    description: 'Collects and surfaces the final result of the agent.',
    inputs: [{ id: 'in', label: 'result', dataType: 'any', required: true }],
    outputs: [],
    config: [],
  },

  // ── Cognitive ──────────────────────────────────────────────────────────────

  {
    type: 'planning.task_decomposition',
    category: 'cognitive',
    label: 'Planning',
    description: 'Decomposes the incoming task into an ordered sequence of sub-steps.',
    inputs: [{ id: 'in', label: 'task', dataType: 'text', required: true }],
    outputs: [{ id: 'plan', label: 'plan', dataType: 'plan', required: false }],
    config: [
      {
        key: 'strategy',
        label: 'Strategy',
        type: 'select',
        default: 'decompose',
        options: [
          { label: 'Decompose', value: 'decompose' },
          { label: 'Goal-first', value: 'goal' },
          { label: 'Multi-step', value: 'multistep' },
        ],
      },
      {
        key: 'maxSteps',
        label: 'Max steps',
        type: 'number',
        default: 5,
        description: 'Upper bound on the number of sub-steps generated.',
      },
    ],
  },

  {
    type: 'verification.critique',
    category: 'cognitive',
    label: 'Verification',
    description: 'Critiques the answer. Routes to "verified" if acceptable, "needs retry" otherwise.',
    inputs: [{ id: 'in', label: 'answer', dataType: 'text', required: true }],
    outputs: [
      { id: 'pass',  label: 'verified',     dataType: 'text', required: false },
      { id: 'retry', label: 'needs retry',  dataType: 'text', required: false },
    ],
    config: [
      {
        key: 'maxRetries',
        label: 'Max retries',
        type: 'number',
        default: 2,
      },
      {
        key: 'criteria',
        label: 'Evaluation criteria',
        type: 'text',
        placeholder: 'Check for factual accuracy and completeness…',
        description: 'What the verifier looks for. Passed verbatim to the LLM judge.',
      },
    ],
  },

  {
    type: 'cognitive.reflection',
    category: 'cognitive',
    label: 'Reflection',
    description: 'Reviews the execution trajectory and extracts actionable insights for future runs.',
    inputs: [
      { id: 'trajectory', label: 'trajectory', dataType: 'any', required: true },
    ],
    outputs: [
      { id: 'insight', label: 'insight', dataType: 'text', required: false },
    ],
    config: [
      {
        key: 'focus',
        label: 'Focus',
        type: 'select',
        default: 'general',
        options: [
          { label: 'General', value: 'general' },
          { label: 'Errors only', value: 'errors' },
          { label: 'Strategy', value: 'strategy' },
        ],
      },
    ],
  },

  // ── Memory ─────────────────────────────────────────────────────────────────

  {
    type: 'memory.buffer',
    category: 'memory',
    label: 'Buffer Memory',
    description: 'Keeps the N most recent messages in a sliding-window buffer.',
    inputs:  [{ id: 'in',      label: 'message', dataType: 'text',     required: true  }],
    outputs: [{ id: 'history', label: 'history', dataType: 'messages', required: false }],
    config: [
      {
        key: 'windowSize',
        label: 'Window size',
        type: 'number',
        default: 10,
        description: 'Maximum number of messages to retain.',
      },
    ],
  },

  {
    type: 'memory.retrieval',
    category: 'memory',
    label: 'Memory Retrieval',
    description: 'Searches a vector store for past context relevant to the current query.',
    inputs:  [{ id: 'query',   label: 'query',   dataType: 'text',     required: true  }],
    outputs: [{ id: 'context', label: 'context', dataType: 'messages', required: false }],
    config: [
      {
        key: 'topK',
        label: 'Top-K results',
        type: 'number',
        default: 3,
      },
      {
        key: 'store',
        label: 'Vector store',
        type: 'select',
        default: 'in_memory',
        options: [
          { label: 'In-memory', value: 'in_memory' },
          { label: 'Chroma',    value: 'chroma'    },
          { label: 'Pinecone',  value: 'pinecone'  },
        ],
      },
    ],
  },

  // ── Model ──────────────────────────────────────────────────────────────────

  {
    type: 'model.inference',
    category: 'model',
    label: 'Model',
    description: 'Calls an LLM with the supplied context. No cognitive structure — pure inference.',
    inputs:  [{ id: 'in',  label: 'context', dataType: 'any',  required: true  }],
    outputs: [{ id: 'out', label: 'answer',  dataType: 'text', required: false }],
    config: [
      {
        key: 'provider',
        label: 'Provider',
        type: 'select',
        default: 'anthropic',
        options: [
          { label: 'Anthropic', value: 'anthropic' },
          { label: 'OpenAI',    value: 'openai'    },
          { label: 'Local',     value: 'local'     },
        ],
      },
      {
        key: 'model',
        label: 'Model',
        type: 'string',
        default: 'claude-sonnet-4-6',
      },
      {
        key: 'systemPrompt',
        label: 'System prompt',
        type: 'text',
        placeholder: 'You are a helpful assistant…',
        description: 'Instructions prepended to every request. Defines the model\'s role.',
      },
      {
        key: 'temperature',
        label: 'Temperature',
        type: 'number',
        default: 0,
      },
      {
        key: 'maxTokens',
        label: 'Max tokens',
        type: 'number',
        default: 1024,
      },
    ],
  },

  // ── Tool ───────────────────────────────────────────────────────────────────

  {
    type: 'tool.web_search',
    category: 'tool',
    label: 'Web Search',
    description: 'Queries a search engine and returns the top results as text.',
    inputs:  [{ id: 'query',   label: 'query',   dataType: 'text', required: true  }],
    outputs: [{ id: 'results', label: 'results', dataType: 'text', required: false }],
    config: [
      {
        key: 'maxResults',
        label: 'Max results',
        type: 'number',
        default: 5,
      },
      {
        key: 'engine',
        label: 'Search engine',
        type: 'select',
        default: 'tavily',
        options: [
          { label: 'Tavily', value: 'tavily' },
          { label: 'Serper', value: 'serper' },
        ],
      },
    ],
  },

  {
    type: 'tool.code_exec',
    category: 'tool',
    label: 'Code Executor',
    description: 'Runs Python code in a sandboxed environment and returns stdout or an error.',
    inputs: [{ id: 'code', label: 'code', dataType: 'text', required: true }],
    outputs: [
      { id: 'result', label: 'result', dataType: 'text', required: false },
      { id: 'error',  label: 'error',  dataType: 'text', required: false },
    ],
    config: [
      {
        key: 'timeout',
        label: 'Timeout (s)',
        type: 'number',
        default: 10,
      },
    ],
  },

  // ── Policy ─────────────────────────────────────────────────────────────────

  {
    type: 'policy.verification',
    category: 'policy',
    label: 'Verification Policy',
    description: 'Routes the answer through verification only when confidence is below threshold.',
    inputs: [{ id: 'in', label: 'answer', dataType: 'text', required: true }],
    outputs: [
      { id: 'verify', label: 'needs check', dataType: 'text', required: false },
      { id: 'pass',   label: 'accepted',    dataType: 'text', required: false },
    ],
    config: [
      {
        key: 'mode',
        label: 'Activation mode',
        type: 'select',
        default: 'confidence',
        options: [
          { label: 'Confidence score', value: 'confidence' },
          { label: 'Always verify',    value: 'always'     },
          { label: 'Never verify',     value: 'never'      },
        ],
      },
      {
        key: 'threshold',
        label: 'Confidence threshold',
        type: 'number',
        default: 0.7,
        description: 'Only used when mode = "confidence". Range 0–1.',
      },
    ],
  },
]
