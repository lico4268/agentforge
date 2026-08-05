import { create } from 'zustand'

export type CanvasNodeMode = 'classic' | 'agent'

/** Pure UI state — panel visibility, etc. No domain data here. */
type UiState = {
  panels: { library: boolean; inspector: boolean; log: boolean }
  canvasNodeMode: CanvasNodeMode
  /** Agent-mode connection dots are hidden by default — direction reads from
   * the edge's arrowhead instead. Toggle this on to drag new connections. */
  showConnectionPorts: boolean
  /** Tier 1/2 loop scope ids the user has drilled into. Absent = collapsed
   * (the default), so newly-detected loops never need to be pre-populated. */
  expandedLoopScopeIds: ReadonlySet<string>
  /** Global override: when true, every loop scope renders as its real
   * members/edges regardless of `expandedLoopScopeIds`. This is the default:
   * users must be able to understand the original execution graph before
   * opting into a derived loop projection. */
  rawExecutionView: boolean
  togglePanel: (key: keyof UiState['panels']) => void
  setCanvasNodeMode: (mode: CanvasNodeMode) => void
  toggleConnectionPorts: () => void
  toggleLoopScopeExpanded: (id: string) => void
  toggleRawExecutionView: () => void
}

export const useUiStore = create<UiState>((set) => ({
  panels: { library: true, inspector: true, log: true },
  canvasNodeMode: 'agent',
  showConnectionPorts: false,
  expandedLoopScopeIds: new Set(),
  rawExecutionView: true,
  togglePanel: (key) =>
    set((s) => ({ panels: { ...s.panels, [key]: !s.panels[key] } })),
  setCanvasNodeMode: (canvasNodeMode) => set({ canvasNodeMode }),
  toggleConnectionPorts: () => set((s) => ({ showConnectionPorts: !s.showConnectionPorts })),
  toggleLoopScopeExpanded: (id) =>
    set((s) => {
      const next = new Set(s.expandedLoopScopeIds)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return { expandedLoopScopeIds: next }
    }),
  toggleRawExecutionView: () => set((s) => ({ rawExecutionView: !s.rawExecutionView })),
}))
