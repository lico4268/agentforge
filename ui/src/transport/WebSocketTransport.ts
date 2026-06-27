import type { Transport } from './Transport'
import {
  ServerMessageSchema,
  type ClientMessage,
  type ServerMessage,
} from './protocol'

/**
 * Real transport for when the FastAPI backend exists. Not wired up yet — the
 * app uses MockTransport for now. Kept here so the seam is concrete: switching
 * is a one-line change in providers. See ui-architecture.md §7.
 */
export class WebSocketTransport implements Transport {
  private ws: WebSocket | null = null
  private handlers = new Set<(msg: ServerMessage) => void>()
  private url: string

  constructor(url: string) {
    this.url = url
  }

  connect() {
    return new Promise<void>((resolve, reject) => {
      this.ws = new WebSocket(this.url)
      this.ws.onopen = () => resolve()
      this.ws.onerror = (e) => reject(e)
      this.ws.onmessage = (e) => {
        const parsed = ServerMessageSchema.safeParse(JSON.parse(e.data))
        if (parsed.success) this.handlers.forEach((h) => h(parsed.data))
      }
    })
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
    this.handlers.clear()
  }

  send(msg: ClientMessage) {
    this.ws?.send(JSON.stringify(msg))
  }

  subscribe(handler: (msg: ServerMessage) => void) {
    this.handlers.add(handler)
    return () => this.handlers.delete(handler)
  }
}
