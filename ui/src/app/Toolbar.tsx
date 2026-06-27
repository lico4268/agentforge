import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTransport } from '@/transport/TransportContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { loadModels } from '@/registry/loadModels'
import type { ModelConfig } from '@/types'

const ARCH_OPTIONS = [
  { value: 'gsm8k-treatment', label: 'GSM8K Treatment (full)' },
  { value: 'gsm8k-baseline',  label: 'GSM8K Baseline (simple)' },
  { value: 'current',         label: 'Current canvas' },
] as const

type ArchOption = (typeof ARCH_OPTIONS)[number]['value']

const PROVIDER_BADGE: Record<string, string> = {
  anthropic: '🟠',
  openai:    '🟢',
  google:    '🔵',
  local:     '⚪',
}

/** Top bar — run the current graph through the transport, reset prior run. */
export function Toolbar() {
  const transport    = useTransport()
  const toArchitecture = useGraphStore((s) => s.toArchitecture)
  const reset        = useExecutionStore((s) => s.reset)
  const nodeCount    = useGraphStore((s) => s.nodes.length)
  const runStatus    = useExecutionStore((s) => s.runStatus)
  const runResult    = useExecutionStore((s) => s.runResult)
  const runError     = useExecutionStore((s) => s.runError)

  const [task, setTask]       = useState('Janet has 3 ducks and 5 chickens. How many animals does she have?')
  const [archName, setArchName] = useState<ArchOption>('gsm8k-treatment')
  const [modelId, setModelId]   = useState<string>('claude-haiku-4-5-20251001')

  // 백엔드에서 모델 목록 fetch
  const { data: models, isError: modelsError } = useQuery({
    queryKey: ['models'],
    queryFn: loadModels,
    staleTime: 60_000,
    retry: 1,
  })

  const selectedModel: ModelConfig | undefined = models?.find((m) => m.id === modelId)
    ?? models?.[0]

  const isRunning = runStatus === 'running'

  const onRun = () => {
    if (!selectedModel) return
    reset()
    const name = archName === 'current' ? 'current-canvas' : archName
    const architecture = toArchitecture(name)
    architecture.metadata.name = name
    transport.send({
      kind: 'run',
      architecture,
      input: { task: task.trim(), task_tags: [] },
      model: { provider: selectedModel.provider, model: selectedModel.id, temperature: 0 },
    })
  }

  return (
    <div className="flex flex-col border-b border-white/5 bg-[#0d111a]">
      <div className="flex items-center justify-between px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-100">Agentforge</span>
          <span className="text-[10px] text-slate-600">v0.1</span>
        </div>

        <div className="flex items-center gap-2">
          {/* 아키텍처 선택 */}
          <select
            value={archName}
            onChange={(e) => setArchName(e.target.value as ArchOption)}
            className="rounded border border-white/10 bg-[#161b27] px-2 py-1 text-xs text-slate-300 focus:outline-none"
          >
            {ARCH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* 모델 선택 — 백엔드 /api/models 기반 */}
          <select
            value={selectedModel?.id ?? ''}
            onChange={(e) => setModelId(e.target.value)}
            disabled={!models}
            className="rounded border border-white/10 bg-[#161b27] px-2 py-1 text-xs text-slate-300 focus:outline-none disabled:opacity-50"
          >
            {!models && (
              <option value="">{modelsError ? '모델 로드 실패' : '로딩 중…'}</option>
            )}
            {models?.map((m) => (
              <option key={m.id} value={m.id} disabled={!m.available}>
                {PROVIDER_BADGE[m.provider] ?? '•'} {m.label}{!m.available ? ' (키 없음)' : ''}
              </option>
            ))}
          </select>

          {/* Run 버튼 */}
          <button
            onClick={onRun}
            disabled={isRunning || !selectedModel || !selectedModel.available || (archName === 'current' && nodeCount === 0)}
            className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isRunning ? '⏳ Running…' : '▶ Run'}
          </button>
        </div>
      </div>

      {/* Task 입력 */}
      <div className="flex items-center gap-2 border-t border-white/5 px-4 py-1.5">
        <span className="shrink-0 text-[10px] text-slate-500">Task</span>
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Enter task for the agent…"
          className="w-full rounded border border-white/10 bg-[#161b27] px-2 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
        />
        {selectedModel && (
          <span className="shrink-0 text-[10px] text-slate-600">
            {PROVIDER_BADGE[selectedModel.provider]} {selectedModel.label}
          </span>
        )}
      </div>

      {/* 실행 결과 배너 */}
      {runStatus === 'complete' && runResult && (
        <div className="border-t border-emerald-900/50 bg-emerald-950/40 px-4 py-1.5 text-xs text-emerald-300">
          ✓ {String(runResult.answer ?? '—')}
          {!!runResult.verdict && (
            <span className="ml-3 text-slate-400">
              Verified: {(runResult.verdict as Record<string, unknown>).passed ? '✓ pass' : '✗ fail'}
            </span>
          )}
        </div>
      )}
      {runStatus === 'error' && runError && (
        <div className="border-t border-red-900/50 bg-red-950/40 px-4 py-1.5 text-xs text-red-300">
          ✗ {runError}
        </div>
      )}
    </div>
  )
}
