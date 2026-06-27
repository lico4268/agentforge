import type { NodeCategory } from '@/types'

/** Single source for category color/label, used by nodes, ports, and library. */
export const CATEGORY_META: Record<
  NodeCategory,
  { label: string; color: string; varName: string }
> = {
  cognitive: { label: 'Cognitive', color: '#8b5cf6', varName: 'cat-cognitive' },
  memory:    { label: 'Memory',    color: '#06b6d4', varName: 'cat-memory' },
  model:     { label: 'Model',     color: '#3b82f6', varName: 'cat-model' },
  tool:      { label: 'Tool',      color: '#10b981', varName: 'cat-tool' },
  policy:    { label: 'Policy',    color: '#f59e0b', varName: 'cat-policy' },
  io:        { label: 'I/O',       color: '#64748b', varName: 'cat-io' },
}
