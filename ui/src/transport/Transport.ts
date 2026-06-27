import type { ClientMessage, ServerMessage } from './protocol'

/**
 * Transport abstraction. The UI talks only to this interface, never to a raw
 * socket. Swap MockTransport → WebSocketTransport when the backend lands; no
 * upper-layer code changes. See ui-architecture.md §7.
 */
export interface Transport {
  connect(): Promise<void>
  disconnect(): void
  send(msg: ClientMessage): void
  /** Returns an unsubscribe function. */
  subscribe(handler: (msg: ServerMessage) => void): () => void
}
