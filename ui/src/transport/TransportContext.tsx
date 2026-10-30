import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useExecutionStore } from '@/execution/useExecutionStore'
import type { Transport } from './Transport'
import { MockTransport } from './MockTransport'
import { WebSocketTransport } from './WebSocketTransport'
import type { ServerMessage } from './protocol'

const TransportContext = createContext<Transport | null>(null)

/**
 * WebSocketTransport if the env var VITE_WS_URL is set, otherwise MockTransport.
 * The actual connection address is derived from the current page's host (Vite proxy /ws → :8000) —
 * a hardcoded host would point at that device's own localhost when accessed from another
 * device on the LAN (e.g. a tablet), silently disconnecting with no response.
 */
function createTransport(): Transport {
  const enabled = import.meta.env.VITE_WS_URL as string | undefined
  if (enabled) {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return new WebSocketTransport(`${proto}://${window.location.host}/ws/run`)
  }
  return new MockTransport()
}

export function TransportProvider({ children }: { children: ReactNode }) {
  const transportRef = useRef<Transport>(createTransport())
  const applyEvent = useExecutionStore((s) => s.applyEvent)
  const setRunState = useExecutionStore((s) => s.setRunState)
  const setInterrupt = useExecutionStore((s) => s.setInterrupt)
  useEffect(() => {
    const transport = transportRef.current
    transport.connect().catch(console.error)

    const unsub = transport.subscribe((msg: ServerMessage) => {
      if (msg.kind === 'event') {
        applyEvent(msg.event)
      } else if (msg.kind === 'run_started') {
        setRunState({ runId: msg.runId, status: 'running', result: null })
      } else if (msg.kind === 'run_complete') {
        setRunState({ runId: msg.runId, status: 'complete', result: msg.result })
      } else if (msg.kind === 'interrupt') {
        setInterrupt(msg.runId, msg.nodeId, msg.payload)
      } else if (msg.kind === 'error') {
        setRunState({ runId: msg.runId ?? null, status: 'error', result: null, error: msg.message })
      }
    })

    return () => {
      unsub()
      transport.disconnect()
    }
  }, [applyEvent, setRunState, setInterrupt])

  return (
    <TransportContext.Provider value={transportRef.current}>
      {children}
    </TransportContext.Provider>
  )
}

export function useTransport(): Transport {
  const t = useContext(TransportContext)
  if (!t) throw new Error('useTransport must be used within TransportProvider')
  return t
}
