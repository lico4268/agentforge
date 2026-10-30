import { z } from 'zod'

/**
 * REST response contract for the arch.yaml store (maps to server/arch_files.py:read_arch_file, Task 5).
 * `architecture` is intentionally unknown — text-first architecture nodes differ in shape from the
 * canvas-era `ArchitectureSchema` (position required): no position, but a `flow` string.
 * The dashboard only views, never authors, so there's no need to redefine the full schema.
 */
export const ArchFileSchema = z.object({
  name: z.string(),
  text: z.string(),
  architecture: z.unknown(),
  warnings: z.array(z.string()),
})
export type ArchFile = z.infer<typeof ArchFileSchema>

export const ArchListItemSchema = z.object({ name: z.string(), size: z.number() })
export type ArchListItem = z.infer<typeof ArchListItemSchema>

/**
 * The minimal shape of `architecture` (unknown) that the dashboard actually reads — the `flow`
 * string handed straight to mermaid, and the authoritative node id list that decides which
 * diagram nodes get coloured (includes synthetic `__guard_N` guards — filtering them out is
 * `deriveFlowStatuses`' job). On parse failure the Dashboard simply omits the diagram
 * (design §3.2 — no conversion code).
 */
export const ArchGraphSchema = z.object({
  flow: z.string().default(''),
  nodes: z.array(z.object({ id: z.string() })).default([]),
})
export type ArchGraph = z.infer<typeof ArchGraphSchema>
