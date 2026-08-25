import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useExecutionStore } from '@/execution/useExecutionStore'
import type { Transport } from './Transport'
import { MockTransport } from './MockTransport'
import { WebSocketTransport } from './WebSocketTransport'
import type { ServerMessage } from './protocol'

const TransportContext = createContext<Transport | null>(null)

/**
 * 환경변수 VITE_WS_URL이 있으면 WebSocketTransport, 없으면 MockTransport.
 * 실제 접속 주소는 현재 페이지의 host에서 유도한다(Vite 프록시 /ws → :8000) —
 * 하드코딩된 host를 쓰면 LAN의 다른 기기(예: 태블릿)에서 접속했을 때
 * 그 기기 자신의 localhost를 가리키게 되어 아무 반응 없이 조용히 끊긴다.
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
