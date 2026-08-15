import { create } from 'zustand'

export type CanvasNodeMode = 'classic' | 'agent'

/** Pure UI state — panel visibility, etc. No domain data here. */
type UiState = {
  panels: { library: boolean; inspector: boolean; log: boolean }
  canvasNodeMode: CanvasNodeMode
  /** Agent-mode connection dots are hidden by default — direction reads from
   * the edge's arrowhead instead. Toggle this on to drag new connections. */
  showConnectionPorts: boolean
  /** Which loop.guard node's drilled-in view is showing, if any. Pure
   * view-layer navigation state — never touches the graph store, so it has
   * no effect on `toArchitecture()`/`compile_graph`. */
  drilledInLoopId: string | null
  togglePanel: (key: keyof UiState['panels']) => void
  setCanvasNodeMode: (mode: CanvasNodeMode) => void
  toggleConnectionPorts: () => void
  enterLoop: (loopNodeId: string) => void
  exitLoop: () => void
}

export const useUiStore = create<UiState>((set) => ({
  panels: { library: true, inspector: true, log: true },
  canvasNodeMode: 'agent',
  showConnectionPorts: false,
  drilledInLoopId: null,
  togglePanel: (key) =>
    set((s) => ({ panels: { ...s.panels, [key]: !s.panels[key] } })),
  // Drill-down only exists conceptually in agent mode — switching modes
  // always exits any drill-down so Canvas (which stops projecting outside
  // agent mode) and Toolbar's breadcrumb never disagree about the state.
  setCanvasNodeMode: (canvasNodeMode) => set({ canvasNodeMode, drilledInLoopId: null }),
  toggleConnectionPorts: () => set((s) => ({ showConnectionPorts: !s.showConnectionPorts })),
  enterLoop: (loopNodeId) => set({ drilledInLoopId: loopNodeId }),
  exitLoop: () => set({ drilledInLoopId: null }),
}))
