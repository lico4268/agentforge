export function viewportTransitionDuration(reducedMotion: boolean) {
  return reducedMotion ? 0 : 200
}

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
