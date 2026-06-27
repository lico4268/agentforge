import { z } from 'zod'
import { ArchitectureSchema, ExecutionEventSchema } from '@/types'

/**
 * Wire protocol between frontend and backend (ui-architecture.md §7 + backend-spec.md §5).
 * Hidden behind the Transport interface so MockTransport and WebSocketTransport are interchangeable.
 */

// Client → Server
export const ClientMessageSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('run'),
    architecture: ArchitectureSchema,
    input: z.object({
      task: z.string(),
      task_tags: z.array(z.string()).default([]),
    }).nullable(),
    model: z.object({
      provider: z.string().default('anthropic'),
      model: z.string().default('claude-haiku-4-5-20251001'),
      temperature: z.number().default(0),
    }).optional(),
  }),
  z.object({ kind: z.literal('stop'), runId: z.string() }),
  // Human Checkpoint 재개 (backend-spec.md §5)
  z.object({
    kind: z.literal('resume'),
    runId: z.string(),
    nodeId: z.string(),
    decision: z.object({
      action: z.enum(['approve', 'revise', 'reject']),
      edits: z.record(z.string(), z.unknown()).optional(),
      reason: z.string().optional(),
    }),
  }),
  // 재접속 시 이벤트 스냅샷 요청
  z.object({ kind: z.literal('reconnect'), runId: z.string() }),
  // v0.3
  z.object({ kind: z.literal('rerun_from'), runId: z.string(), nodeId: z.string() }),
  z.object({ kind: z.literal('update_node'), nodeId: z.string(), config: z.record(z.string(), z.unknown()) }),
])
export type ClientMessage = z.infer<typeof ClientMessageSchema>

// Server → Client
export const ServerMessageSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('event'), event: ExecutionEventSchema }),
  z.object({ kind: z.literal('state'), runId: z.string().optional(), snapshot: z.unknown() }),
  z.object({ kind: z.literal('error'), runId: z.string().optional(), message: z.string() }),
  // 실행 시작/완료
  z.object({ kind: z.literal('run_started'), runId: z.string() }),
  z.object({
    kind: z.literal('run_complete'),
    runId: z.string(),
    result: z.object({
      answer: z.string().nullable().optional(),
      verdict: z.record(z.string(), z.unknown()).nullable().optional(),
      confidence: z.number().nullable().optional(),
    }),
  }),
  // Human Checkpoint 정지 알림 (backend-spec.md §5)
  z.object({
    kind: z.literal('interrupt'),
    runId: z.string(),
    nodeId: z.string(),
    payload: z.object({
      summary: z.string(),
      fields: z.record(z.string(), z.unknown()),
      actions: z.array(z.enum(['approve', 'revise', 'reject'])),
    }),
  }),
])
export type ServerMessage = z.infer<typeof ServerMessageSchema>
