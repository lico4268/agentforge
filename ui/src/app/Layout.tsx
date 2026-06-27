import { ReactFlowProvider } from '@xyflow/react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { Canvas } from '@/canvas/Canvas'
import { NodeLibrary } from '@/panels/NodeLibrary'
import { Inspector } from '@/panels/Inspector'
import { LogPanel } from '@/panels/LogPanel'
import { Toolbar } from './Toolbar'

const vHandle = (
  <Separator className="w-px shrink-0 bg-white/5 transition-colors hover:bg-white/20" />
)
const hHandle = (
  <Separator className="h-px shrink-0 bg-white/5 transition-colors hover:bg-white/20" />
)

/**
 * Left library · center canvas+log · right inspector.
 *
 * react-resizable-panels v4: numeric size props (minSize, maxSize, defaultSize)
 * are in PIXELS. Pass explicit percentage strings ("16%") for percentage-based
 * sizing. defaultLayout still uses 0–100 numbers.
 */
export function Layout() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Toolbar />
      <div className="min-h-0 flex-1">
        <Group
          orientation="horizontal"
          defaultLayout={{ library: 16, center: 60, inspector: 24 }}
          style={{ height: '100%' }}
        >
          <Panel id="library" defaultSize="16%" minSize="10%" maxSize="28%">
            <NodeLibrary />
          </Panel>
          {vHandle}
          <Panel id="center">
            <Group
              orientation="vertical"
              defaultLayout={{ canvas: 70, log: 30 }}
              style={{ height: '100%' }}
            >
              <Panel id="canvas" minSize="30%">
                <ReactFlowProvider>
                  <Canvas />
                </ReactFlowProvider>
              </Panel>
              {hHandle}
              <Panel id="log" minSize="12%">
                <LogPanel />
              </Panel>
            </Group>
          </Panel>
          {vHandle}
          <Panel id="inspector" defaultSize="24%" minSize="14%" maxSize="36%">
            <Inspector />
          </Panel>
        </Group>
      </div>
    </div>
  )
}
