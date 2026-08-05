const CONDITIONAL_HANDLES = new Set(['accept', 'refine', 'clarify', 'approve', 'revise', 'reject'])

export function edgePresentation(sourceHandle?: string | null) {
  const conditional = Boolean(sourceHandle && CONDITIONAL_HANDLES.has(sourceHandle))
  const color =
    sourceHandle === 'accept' || sourceHandle === 'approve'
      ? '#4edea3'
      : sourceHandle === 'clarify' || sourceHandle === 'revise'
        ? '#ffd180'
        : sourceHandle === 'reject'
          ? '#ff8a80'
          : '#6f8175'

  return { conditional, color }
}
