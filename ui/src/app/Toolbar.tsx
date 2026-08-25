import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTransport } from '@/transport/TransportContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { useUiStore } from '@/stores/useUiStore'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { loadModels } from '@/registry/loadModels'
import { deriveLoopMembers } from '@/canvas/loop/deriveLoopMembers'
import { OpenRouterFavoritesModal } from './OpenRouterFavoritesModal'
import type { ModelConfig } from '@/types'

const ARCH_OPTIONS = [
  { value: 'gsm8k-treatment', label: 'GSM8K Treatment' },
  { value: 'gsm8k-baseline',  label: 'GSM8K Baseline'  },
  { value: 'current',         label: 'Current Canvas'  },
] as const

type ArchOption = (typeof ARCH_OPTIONS)[number]['value']

export function Toolbar() {
  const transport      = useTransport()
  const toArchitecture = useGraphStore((s) => s.toArchitecture)
  const reset          = useExecutionStore((s) => s.reset)
  const nodes = useGraphStore((s) => s.nodes)
  const nodeCount = nodes.length
  const runStatus      = useExecutionStore((s) => s.runStatus)

  const drilledInLoopId = useUiStore((s) => s.drilledInLoopId)
  const exitLoop = useUiStore((s) => s.exitLoop)
  const edges = useGraphStore((s) => s.edges)
  const drilledInLoopMemberCount = drilledInLoopId
    ? deriveLoopMembers(nodes.map((n) => n.id), edges, drilledInLoopId).length
    : 0

  const [archName, setArchName] = useState<ArchOption>('gsm8k-treatment')
  const [modelId, setModelId]   = useState<string>('openrouter/auto')
  const [favoritesOpen, setFavoritesOpen] = useState(false)

  const { data: models, isError: modelsError } = useQuery({
    queryKey: ['models'],
    queryFn: loadModels,
    staleTime: 60_000,
    retry: 1,
  })

  const inputSample = nodes.find((n) => n.data.manifestType === 'io.input')?.data.config?.sample
  const task = typeof inputSample === 'string' ? inputSample.trim() : ''

  // 'current' 캔버스는 노드별 Model Slots(Inspector)가 모델을 결정한다 — 상단 모델
  // 선택은 그 값을 조용히 덮어쓰지 않도록 고정 아키텍처(baseline/treatment)에서만 쓴다.
  const usesToolbarModel = archName !== 'current'

  const selectedModel: ModelConfig | undefined =
    models?.find((m) => m.id === modelId) ?? models?.[0]

  const isRunning = runStatus === 'running' || runStatus === 'paused'

  const onRun = () => {
    if (usesToolbarModel && !selectedModel) return
    reset()
    const name = archName === 'current' ? 'current-canvas' : archName
    const architecture = toArchitecture(name)
    architecture.metadata.name = name
    transport.send({
      kind: 'run',
      architecture,
      input: { task, task_tags: [] },
      model: usesToolbarModel && selectedModel
        ? { provider: selectedModel.provider, model: selectedModel.id, temperature: 0 }
        : undefined,
    })
  }

  return (
    <div className="shrink-0 border-b border-[#3c4a42] bg-[#1a211d]">
      {/* Single-row toolbar */}
      <div className="flex h-14 items-center gap-3 px-4">

        {/* Logo, or a breadcrumb back to the main graph while drilled into a loop */}
        {drilledInLoopId ? (
          <button
            type="button"
            onClick={exitLoop}
            className="flex shrink-0 items-center gap-1.5 text-[13px] font-semibold text-[#dde4dd] transition-colors hover:text-[#4edea3]"
            title="Back to main graph"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>arrow_back</span>
            Agentforge <span className="font-normal text-[#86948a]">/</span> Loop
            <span className="rounded border border-[#a78bfa]/40 bg-[#a78bfa]/10 px-1.5 py-px font-mono text-[10px] text-[#a78bfa]">
              {drilledInLoopMemberCount} node{drilledInLoopMemberCount === 1 ? '' : 's'}
            </span>
          </button>
        ) : (
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-[15px] font-semibold tracking-tight text-[#dde4dd]">Agentforge</span>
            <span className="rounded border border-[#3c4a42]/60 bg-[#2f3632]/60 px-1.5 py-px font-mono text-[10px] text-[#86948a]">
              v0.1
            </span>
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right controls */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Settings icon — OpenRouter favorites */}
          <button
            onClick={() => setFavoritesOpen(true)}
            title="OpenRouter favorites"
            className="flex h-8 w-8 items-center justify-center rounded text-[#86948a] transition-colors hover:bg-[#242c27] hover:text-[#dde4dd]"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>settings</span>
          </button>

          <div className="h-5 w-px bg-[#3c4a42]" />

          {/* Architecture select */}
          <select
            value={archName}
            onChange={(e) => setArchName(e.target.value as ArchOption)}
            className="rounded border border-[#3c4a42] bg-[#242c27] px-3 py-1.5 text-[12px] text-[#dde4dd] outline-none transition-colors focus:border-[#4edea3]"
          >
            {ARCH_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Model select — 고정 아키텍처(baseline/treatment) 전용. 'Current Canvas'는
              노드별 Model Slots가 모델을 결정하므로 여기서 숨긴다(상충 방지). */}
          {usesToolbarModel ? (
            <select
              value={selectedModel?.id ?? ''}
              onChange={(e) => setModelId(e.target.value)}
              disabled={!models}
              className="rounded border border-[#3c4a42] bg-[#242c27] px-3 py-1.5 text-[12px] text-[#dde4dd] outline-none transition-colors focus:border-[#4edea3] disabled:opacity-50"
            >
              {!models && (
                <option value="">{modelsError ? 'Load failed' : 'Loading…'}</option>
              )}
              {models?.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.label}{!m.available ? ' (no key)' : ''}
                </option>
              ))}
            </select>
          ) : (
            <span
              className="rounded border border-[#3c4a42]/60 px-3 py-1.5 font-mono text-[10px] text-[#86948a]"
              title="Model Slots가 각 노드의 모델을 결정합니다 (Inspector)"
            >
              Model: per-node
            </span>
          )}

          {/* Run button */}
          <button
            onClick={onRun}
            disabled={
              isRunning ||
              !task ||
              (usesToolbarModel && (!selectedModel || !selectedModel.available)) ||
              (archName === 'current' && nodeCount === 0)
            }
            className="flex items-center gap-1.5 rounded bg-[#4edea3] px-4 py-1.5 text-[12px] font-bold text-[#003824] shadow-[0_0_10px_rgba(78,222,163,0.25)] transition-all hover:bg-[#6ffbbe] hover:shadow-[0_0_16px_rgba(78,222,163,0.45)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14, fontVariationSettings: "'FILL' 1" }}>
              play_arrow
            </span>
            {runStatus === 'paused' ? 'Waiting for review…' : isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      <OpenRouterFavoritesModal open={favoritesOpen} onClose={() => setFavoritesOpen(false)} />
    </div>
  )
}
