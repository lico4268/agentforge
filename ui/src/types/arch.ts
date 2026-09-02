import { z } from 'zod'

/**
 * arch.yaml 저장소 REST 응답 계약 (server/arch_files.py:read_arch_file 대응, Task 5).
 * `architecture`는 의도적으로 unknown — 텍스트 우선 아키텍처의 노드는 캔버스 시절
 * `ArchitectureSchema`(position 필수)와 모양이 다르고(포지션 없음, `flow` 문자열 있음),
 * 대시보드는 저작이 아니라 조회만 하므로 전체 스키마를 다시 정의할 필요가 없다.
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
 * `architecture`(unknown) 중 대시보드가 실제로 읽는 최소 형태 — mermaid에 그대로
 * 넘길 `flow` 문자열뿐이다. 파싱 실패 시 Dashboard는 다이어그램을 그냥 생략한다
 * (설계 §3.2 — 변환 코드를 두지 않는다).
 */
export const ArchGraphSchema = z.object({
  flow: z.string().default(''),
})
export type ArchGraph = z.infer<typeof ArchGraphSchema>
