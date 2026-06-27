import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTransport } from '@/transport/TransportContext'
import { useGraphStore } from '@/stores/useGraphStore'
import { useExecutionStore } from '@/execution/useExecutionStore'
import { loadModels } from '@/registry/loadModels'
import type { ModelConfig } from '@/types'

const ARCH_OPTIONS = [
  { value: 'gsm8k-treatment', label: 'GSM8K Treatment' },
  { value: 'gsm8k-baseline',  label: 'GSM8K Baseline'  },
  { value: 'current',         label: 'Current Canvas'  },
] as const

type ArchOption = (typeof ARCH_OPTIONS)[number]['value']

const PROVIDER_COLOR: Record<string, string> = {
  anthropic: '#f97316',
  openai:    '#10b981',
  google:    '#3b82f6',
  local:     '#64748b',
}

export function Toolbar() {
  const transport      = useTransport()
  const toArchitecture = useGraphStore((s) => s.toArchitecture)
  const reset          = useExecutionStore((s) => s.reset)
  const nodeCount      = useGraphStore((s) => s.nodes.length)
  const runStatus      = useExecutionStore((s) => s.runStatus)
  const runResult      = useExecutionStore((s) => s.runResult)
  const runError       = useExecutionStore((s) => s.runError)

  const [task, setTask]         = useState('Janet has 3 ducks and 5 chickens. How many animals does she have?')
  const [archName, setArchName] = useState<ArchOption>('gsm8k-treatment')
  const [modelId, setModelId]   = useState<string>('claude-haiku-4-5-20251001')

  const { data: models, isError: modelsError } = useQuery({
    queryKey: ['models'],
    queryFn: loadModels,
    staleTime: 60_000,
    retry: 1,
  })

  const selectedModel: ModelConfig | undefined =
    models?.find((m) => m.id === modelId) ?? models?.[0]

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
    <div className="shrink-0 border-b border-[#3c4a42] bg-[#1a211d]">
      {/* Single-row toolbar */}
      <div className="flex h-14 items-center gap-3 px-4">

        {/* Logo */}
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[15px] font-semibold tracking-tight text-[#dde4dd]">Agentforge</span>
          <span className="rounded border border-[#3c4a42]/60 bg-[#2f3632]/60 px-1.5 py-px font-mono text-[10px] text-[#86948a]">
            v0.1
          </span>
        </div>

        {/* Task input — takes remaining center space */}
        <div className="flex flex-1 items-center gap-2 rounded border border-[#3c4a42] bg-[#161d19] px-3 py-1.5 transition-all focus-within:border-[#4edea3] focus-within:shadow-[0_0_0_2px_rgba(78,222,163,0.12)]">
          <span className="shrink-0 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#86948a]">
            Task
          </span>
          <input
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Enter task for the agent…"
            className="w-full bg-transparent text-[13px] text-[#dde4dd] outline-none placeholder:text-[#3c4a42]"
          />
          {selectedModel && (
            <div className="flex shrink-0 items-center gap-1.5 border-l border-[#3c4a42]/60 pl-3">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: PROVIDER_COLOR[selectedModel.provider] ?? '#64748b' }}
              />
              <span className="font-mono text-[11px] text-[#bbcabf]">{selectedModel.label}</span>
            </div>
          )}
        </div>

        {/* Right controls */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Settings icon */}
          <button className="flex h-8 w-8 items-center justify-center rounded text-[#86948a] transition-colors hover:bg-[#242c27] hover:text-[#dde4dd]">
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

          {/* Model select */}
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

          {/* Run button */}
          <button
            onClick={onRun}
            disabled={
              isRunning ||
              !selectedModel ||
              !selectedModel.available ||
              (archName === 'current' && nodeCount === 0)
            }
            className="flex items-center gap-1.5 rounded bg-[#4edea3] px-4 py-1.5 text-[12px] font-bold text-[#003824] shadow-[0_0_10px_rgba(78,222,163,0.25)] transition-all hover:bg-[#6ffbbe] hover:shadow-[0_0_16px_rgba(78,222,163,0.45)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14, fontVariationSettings: "'FILL' 1" }}>
              play_arrow
            </span>
            {isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      {/* Result / error banner */}
      {runStatus === 'complete' && runResult && (
        <div className="border-t border-[#003824]/80 bg-[#002113]/60 px-4 py-1.5 font-mono text-[12px] text-[#4edea3]">
          ✓ {String(runResult.answer ?? '—')}
          {!!runResult.verdict && (
            <span className="ml-3 text-[#86948a]">
              Verified:{' '}
              {(runResult.verdict as Record<string, unknown>).passed ? '✓ pass' : '✗ fail'}
            </span>
          )}
        </div>
      )}
      {runStatus === 'error' && runError && (
        <div className="border-t border-[#93000a]/80 bg-[#410005]/40 px-4 py-1.5 font-mono text-[12px] text-[#ffb4ab]">
          ✗ {runError}
        </div>
      )}
    </div>
  )
}
