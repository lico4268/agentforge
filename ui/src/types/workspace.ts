import { z } from 'zod'

/**
 * Workspace file contracts — run output files persisted by the backend.
 * Mirrors server/workspace.py's list_run_files / read_run_file (camelCase).
 */

export const RunFileSchema = z.object({
  name: z.string(),
  nodeId: z.string(),
  sizeBytes: z.number(),
})
export type RunFile = z.infer<typeof RunFileSchema>

export const RunFileContentSchema = z.object({
  name: z.string(),
  content: z.string(),
})
export type RunFileContent = z.infer<typeof RunFileContentSchema>