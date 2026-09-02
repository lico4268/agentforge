import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTransport } from '@/transport/TransportContext'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { loadArchFiles, loadArchFile } from '@/registry/loadArchFiles'
import { ArchGraphSchema } from '@/types/arch'
import { FlowDiagram } from './FlowDiagram'
import { NodeProgress } from './NodeProgress'
import { buildProgressEntries, deriveFlowStatuses } from './buildProgressEntries'

/**
 * 읽기 전용 대시보드 — 저작(캔버스 편집)은 없다. arch.yaml 목록에서 파일을
 * 고르면 서버가 이미 파싱해준 `flow` 문자열을 mermaid에 그대로 넘겨 그림을
 * 얻는다(레이아웃 코드 0줄, 설계 §3.2). 실행은 기존 WS 트랜스포트/스토어를
 * 그대로 재사용한다 — Run·체크포인트 승인/반려는 런타임 동작이라 "저작
 * read-only" 원칙과 무관하다(task-6 브리프 GLOBAL CONSTRAINTS).
 */
export function Dashboard() {
  const transport = useTransport()
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [task, setTask] = useState('')

  const {
    data: archList,
    error: archListError,
  } = useQuery({
    queryKey: ['arch-list'],
    queryFn: loadArchFiles,
    staleTime: 60_000,
  })

  const activeName = selectedName ?? archList?.[0]?.name ?? null

  const {
    data: archFile,
    error: archError,
  } = useQuery({
    queryKey: ['arch-file', activeName],
    queryFn: () => loadArchFile(activeName!),
    enabled: activeName != null,
  })

  const events = useExecutionStore((s) => s.events)
  const runId = useExecutionStore((s) => s.runId)
  const runStatus = useExecutionStore((s) => s.runStatus)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)
  const runError = useExecutionStore((s) => s.runError)
  const reset = useExecutionStore((s) => s.reset)

  const graph = archFile ? ArchGraphSchema.safeParse(archFile.architecture) : null
  const flow = graph?.success ? graph.data.flow : ''
  // 다이어그램 색칠 대상은 서버가 이미 파싱해준 architecture.nodes[].id에서만
  // 뽑는다 — flow 문자열을 정규식으로 재토큰화하면 한글 등 비ASCII id를 못
  // 잡는다(리뷰 finding 1). __guard_N 제외는 deriveFlowStatuses의 책임.
  const nodeIds = graph?.success ? graph.data.nodes.map((n) => n.id) : []

  const entries = buildProgressEntries(events, pendingInterrupt)
  const statuses = deriveFlowStatuses(entries, nodeIds)

  const isBusy = runStatus === 'running' || runStatus === 'paused'

  const onRun = () => {
    if (!activeName) return
    reset()
    transport.send({
      kind: 'run',
      archFile: activeName,
      input: { task, task_tags: [] },
    })
  }

  const onResume = (decision: string) => {
    if (!runId || !pendingInterrupt) return
    transport.send({
      kind: 'resume',
      runId,
      nodeId: pendingInterrupt.nodeId,
      decision: { action: decision as 'approve' | 'revise' | 'reject' },
    })
  }

  return (
    <div className="flex h-screen flex-col gap-3 overflow-auto bg-[#09100c] p-4 text-[13px] text-[#dde4dd]">
      <header className="flex shrink-0 items-center gap-2">
        <span className="text-[15px] font-semibold tracking-tight">Agentforge</span>
        <select
          value={activeName ?? ''}
          onChange={(e) => setSelectedName(e.target.value)}
          className="rounded border border-[#3c4a42] bg-[#242c27] px-2 py-1"
        >
          {!archList && (
            <option value="">{archListError ? 'Failed to load' : 'Loading…'}</option>
          )}
          {archList?.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="task input"
          className="flex-1 rounded border border-[#3c4a42] bg-[#242c27] px-2 py-1"
        />
        <button
          type="button"
          onClick={onRun}
          disabled={!activeName || isBusy}
          className="rounded bg-[#4edea3] px-4 py-1.5 font-bold text-[#003824] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {runStatus === 'paused' ? 'Waiting for review…' : runStatus === 'running' ? 'Running…' : 'Run'}
        </button>
      </header>

      {archListError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          Failed to load arch file list: {(archListError as Error).message}
        </div>
      )}

      {archList && archList.length === 0 && (
        <div className="shrink-0 rounded border border-[#3c4a42] px-3 py-2 text-[#86948a]">
          No arch files found in server/arch/.
        </div>
      )}

      {archError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          {(archError as Error).message}
        </div>
      )}

      {archFile && archFile.warnings.length > 0 && (
        <ul className="shrink-0 rounded border border-[#ffd180]/50 bg-[#ffd180]/10 px-3 py-2 text-[#ffd180]">
          {archFile.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}

      {/* 파일 로드 배너(위) 다음, 다이어그램/진행 목록(아래) 바로 위에 배치 —
          "무엇을 실행했는데 왜 실패했는지"는 실행 결과이므로 그 결과를 보여줄
          자리 바로 앞이 맞다. 파일 로드 에러와 동시에 떠도 서로 겹치지 않고
          위아래로 쌓인다(경쟁하지 않음). 스토어의 runError를 그대로 읽으므로
          reset()/다음 run_started가 오면 (둘 다 runError를 null로 되돌린다)
          자동으로 사라진다 — 별도 dismiss 로직 없음. */}
      {runError && (
        <div className="shrink-0 rounded border border-[#ff8a80]/50 bg-[#ff8a80]/10 px-3 py-2 text-[#ff8a80]">
          {runError}
        </div>
      )}

      {flow && <FlowDiagram flow={flow} statuses={statuses} />}

      <div className="min-h-0 flex-1 overflow-auto">
        <NodeProgress entries={entries} onResume={onResume} />
      </div>
    </div>
  )
}
