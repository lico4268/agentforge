import type { NodeCategory } from '@/types'

export const CATEGORY_META: Record<
  NodeCategory,
  { label: string; color: string; varName: string; icon: string }
> = {
  cognitive: { label: 'Cognitive', color: '#b388ff', varName: 'cat-cognitive', icon: 'psychology'     },
  memory:    { label: 'Memory',    color: '#18ffff', varName: 'cat-memory',    icon: 'memory'         },
  model:     { label: 'Model',     color: '#82b1ff', varName: 'cat-model',     icon: 'smart_toy'      },
  tool:      { label: 'Tool',      color: '#10b981', varName: 'cat-tool',      icon: 'build'          },
  policy:    { label: 'Policy',    color: '#ff8a80', varName: 'cat-policy',    icon: 'policy'         },
  human:     { label: 'Human',     color: '#f43f5e', varName: 'cat-human',     icon: 'person_check'   },
  io:        { label: 'I/O',       color: '#ffd180', varName: 'cat-io',        icon: 'swap_horiz'     },
}

/** Loop-purple — reserved for loop-related UI (re-entry edges, the collapsed
 * loop node's ripple halo). Never mixed with a category color. */
export const LOOP_ACCENT_COLOR = '#a78bfa'

/** Per-node type icons for the library panel */
export const NODE_TYPE_ICONS: Record<string, string> = {
  'planning.decompose': 'psychology',
  'reasoning.cot':      'account_tree',
  'review.intent':      'rule',
  'human.checkpoint':   'person_check',
  'model.binding':      'smart_toy',
  'io.input':           'login',
  'io.output':          'logout',
}
