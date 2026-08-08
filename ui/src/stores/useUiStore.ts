import { create } from 'zustand'

export type CanvasNodeMode = 'classic' | 'agent'

/** Pure UI state — panel visibility, etc. No domain data here. */
type UiState = {
  panels: { library: boolean; inspector: boolean; log: boolean }
  canvasNodeMode: CanvasNodeMode
  /** Agent-mode connection dots are hidden by default — direction reads from
   * the edge's arrowhead instead. Toggle this on to drag new connections. */
  showConnectionPorts: boolean
  togglePanel: (key: keyof UiState['panels']) => void
  setCanvasNodeMode: (mode: CanvasNodeMode) => void
  toggleConnectionPorts: () => void
}

export const useUiStore = create<UiState>((set) => ({
  panels: { library: true, inspector: true, log: true },
  canvasNodeMode: 'agent',
  showConnectionPorts: false,
  togglePanel: (key) =>
    set((s) => ({ panels: { ...s.panels, [key]: !s.panels[key] } })),
  setCanvasNodeMode: (canvasNodeMode) => set({ canvasNodeMode }),
  toggleConnectionPorts: () => set((s) => ({ showConnectionPorts: !s.showConnectionPorts })),
}))
