import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useExecutionStore } from '@/execution/useExecutionStore'
import type { Transport } from './Transport'
import { MockTransport } from './MockTransport'
import { WebSocketTransport } from './WebSocketTransport'
import type { ServerMessage } from './protocol'

const TransportContext = createContext<Transport | null>(null)

/**
 * 환경변수 VITE_WS_URL이 있으면 WebSocketTransport, 없으면 MockTransport.
 * 백엔드 연결: VITE_WS_URL=ws://localhost:8000/ws/run
 */
function createTransport(): Transport {
  const wsUrl = import.meta.env.VITE_WS_URL as string | undefined
  if (wsUrl) {
    return new WebSocketTransport(wsUrl)
  }
  return new MockTransport()
}

export function TransportProvider({ children }: { children: ReactNode }) {
  const transportRef = useRef<Transport>(createTransport())
  const applyEvent = useExecutionStore((s) => s.applyEvent)
  const setRunState = useExecutionStore((s) => s.setRunState)
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
      } else if (msg.kind === 'error') {
        setRunState({ runId: msg.runId ?? null, status: 'error', result: null, error: msg.message })
      }
    })

    return () => {
      unsub()
      transport.disconnect()
    }
  }, [applyEvent, setRunState])

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
