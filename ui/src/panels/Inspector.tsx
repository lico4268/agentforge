import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useGraphStore } from '@/stores/useGraphStore'
import { useNodeRuntime, useExecutionStore } from '@/execution/useExecutionStore'
import { useRegistry } from '@/registry/RegistryContext'
import { CATEGORY_META } from '@/lib/categoryStyle'
import { loadModels } from '@/registry/loadModels'
import { Markdown } from '@/panels/Markdown'
import { CheckpointActions } from '@/canvas/nodes/CheckpointActions'
import type { ConfigField, ModelConfig, ModelSlot } from '@/types'

export function Inspector() {
  const registry = useRegistry()
  const selectedId = useGraphStore((s) => s.selectedNodeId)
  const node = useGraphStore((s) => s.nodes.find((n) => n.id === s.selectedNodeId))
  const updateNodeConfig = useGraphStore((s) => s.updateNodeConfig)
  const edges = useGraphStore((s) => s.edges)
  const allNodes = useGraphStore((s) => s.nodes)
  const removeEdge = useGraphStore((s) => s.removeEdge)
  const runtime = useNodeRuntime(selectedId ?? '')
  const runResult = useExecutionStore((s) => s.runResult)
  const runStatus = useExecutionStore((s) => s.runStatus)
  const runId = useExecutionStore((s) => s.runId)
  const pendingInterrupt = useExecutionStore((s) => s.pendingInterrupt)

  const { data: models } = useQuery({
    queryKey: ['models'],
    queryFn: loadModels,
    staleTime: 60_000,
    retry: 1,
  })

  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-[#161d19]/80 backdrop-blur-xl p-6 text-center">
        <span className="material-symbols-outlined text-[#3c4a42]" style={{ fontSize: 40 }}>
          account_tree
        </span>
        <p className="text-[12px] text-[#86948a]">Select a node to inspect its config and I/O.</p>
      </div>
    )
  }

  const manifest = registry.get(node.data.manifestType)
  if (!manifest) return null

  const meta = CATEGORY_META[manifest.category]
  const config = node.data.config
  const setField = (key: string, value: unknown) =>
    updateNodeConfig(node.id, { ...config, [key]: value })
  const isPendingCheckpoint =
    manifest.type === 'human.checkpoint' && pendingInterrupt?.nodeId === node.id && runId

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#161d19]/80 backdrop-blur-xl">
      {/* Node header */}
      <div className="relative shrink-0 overflow-hidden border-b border-[#3c4a42]/50 px-5 py-4">
        {/* Accent glow */}
        <div
          className="pointer-events-none absolute right-0 top-0 h-24 w-24 rounded-full blur-[50px]"
          style={{ background: `${meta.color}12` }}
        />
        <div className="flex items-center gap-2">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ background: meta.color, boxShadow: `0 0 8px ${meta.color}99` }}
          />
          <h2 className="text-[15px] font-semibold tracking-wide text-[#dde4dd]">{manifest.label}</h2>
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[#86948a]">{manifest.description}</p>
        <div className="mt-2.5 flex items-center gap-2">
          <span className="flex items-center gap-1 rounded border border-[#3c4a42] bg-[#2f3632] px-2 py-0.5 font-mono text-[10px] text-[#bbcabf]">
            <span className="material-symbols-outlined" style={{ fontSize: 11 }}>
              {meta.icon}
            </span>
            {meta.label}
          </span>
          {runtime && runtime.callCount > 0 && (
            <span className="flex items-center gap-1 rounded border border-[#3c4a42] bg-[#2f3632] px-2 py-0.5 font-mono text-[10px] text-[#bbcabf]">
              <span className="material-symbols-outlined" style={{ fontSize: 11 }}>schedule</span>
              {(runtime.totalDurationMs / Math.max(1, runtime.callCount)).toFixed(0)} ms avg
            </span>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-6">

        {/* FINAL RESULT section — output 노드 전용 최종 결과 표시 */}
        {manifest.type === 'io.output' && (
          <FinalResult
            result={pickFinalResult(runtime?.lastOutput, runResult)}
            runStatus={runStatus}
          />
        )}

        {isPendingCheckpoint && (
          <section className="flex flex-col gap-3 rounded-lg border border-[#ffd180]/30 bg-[#ffd180]/5 p-3">
            <div>
              <h3 className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#ffd180]">
                Review decision required
              </h3>
              <p className="mt-1 text-[11px] text-[#bbcabf]">
                Resume this paused checkpoint with a decision.
              </p>
            </div>
            <CheckpointActions
              nodeId={node.id}
              runId={runId!}
              actions={pendingInterrupt?.payload.actions}
            />
          </section>
        )}

        {/* MODEL SLOTS section */}
        {manifest.maxModelSlots && (
          <ModelSlotsEditor
            slots={(config.modelSlots as ModelSlot[] | undefined) ?? []}
            maxSlots={manifest.maxModelSlots}
            models={models}
            onChange={(slots) => setField('modelSlots', slots)}
            accent={meta.color}
          />
        )}

        {/* CONFIG section */}
        {manifest.config.length > 0 && (
          <section className="flex flex-col gap-4">
            <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
              Config
            </h3>
            {manifest.config.map((field) => (
              <Field
                key={field.key}
                field={field}
                value={config[field.key] ?? field.default}
                onChange={(v) => setField(field.key, v)}
                models={models}
                currentProvider={String(config['provider'] ?? 'anthropic')}
              />
            ))}
          </section>
        )}

        {/* CONNECTIONS section */}
        {edges.filter(e => e.source === node.id).length > 0 && (
          <section className="flex flex-col gap-3 border-t border-[#3c4a42]/30 pt-5">
            <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
              Connections (Output)
            </h3>
            <div className="flex flex-col gap-2">
              {edges.filter(e => e.source === node.id).map(edge => {
                const targetNode = allNodes.find(n => n.id === edge.target)
                const targetManifest = targetNode ? registry.get(targetNode.data.manifestType) : null
                const targetLabel = targetManifest ? targetManifest.label : edge.target

                return (
                  <div key={edge.id} className="flex items-center justify-between rounded-md border border-[#3c4a42] bg-[#09100c] p-2">
                    <div className="flex flex-col">
                      <span className="text-[11px] text-[#dde4dd]">To: {targetLabel}</span>
                      <span className="font-mono text-[10px] text-[#86948a]">Port: {edge.targetHandle || 'in'}</span>
                    </div>
                    <button
                      onClick={() => removeEdge(edge.id)}
                      className="flex h-6 w-6 items-center justify-center rounded hover:bg-[#ff8a80]/20 text-[#86948a] hover:text-[#ff8a80] transition-colors"
                      title="Remove Connection"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete</span>
                    </button>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* LAST I/O STATE section */}
        {runtime && runtime.callCount > 0 && runtime.lastOutput !== undefined && (
          <section className="flex flex-col gap-3 border-t border-[#3c4a42]/30 pt-5">
            <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
              Last I/O State
            </h3>
            <IOBlock label="Output" value={runtime.lastOutput} />
          </section>
        )}

        {/* EXECUTION METRICS section */}
        {runtime && runtime.callCount > 0 && (
          <section className="flex flex-col gap-3 border-t border-[#3c4a42]/30 pt-5 pb-4">
            <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
              Execution Metrics
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <MetricCard label="Calls"    value={String(runtime.callCount)} />
              <MetricCard label="Duration" value={`${runtime.totalDurationMs} ms`} />
              <MetricCard label="Tokens"   value={String(runtime.totalTokens)} />
              <MetricCard
                label="Status"
                value={runtime.status}
                accent={statusColor(runtime.status)}
              />
            </div>
            {(runtime.lastModel || runtime.lastAttempt || runtime.fallbackUsed) && (
              <div className="flex flex-wrap gap-1.5">
                {runtime.lastModel && (
                  <span className="rounded border border-[#3c4a42] bg-[#242c27] px-2 py-0.5 font-mono text-[10px] text-[#bbcabf]">
                    model: {runtime.lastModel}
                  </span>
                )}
                {runtime.lastAttempt !== undefined && runtime.lastAttempt > 0 && (
                  <span className="rounded border border-[#ffd180]/30 bg-[#242c27] px-2 py-0.5 font-mono text-[10px] text-[#ffd180]">
                    retries: {runtime.lastAttempt}
                  </span>
                )}
                {runtime.fallbackUsed && (
                  <span className="rounded border border-[#ff8a80]/30 bg-[#242c27] px-2 py-0.5 font-mono text-[10px] text-[#ff8a80]">
                    fallback used
                  </span>
                )}
              </div>
            )}
            {runtime.policyDecision && (
              <div className="rounded border border-[#3c4a42] bg-[#242c27] px-3 py-2 text-[11px]">
                <span className="text-[#86948a]">Policy: </span>
                <span className={runtime.policyDecision.activated ? 'text-[#ff8a80]' : 'text-[#4edea3]'}>
                  {runtime.policyDecision.activated ? 'activated' : 'skipped'}
                </span>
                {' — '}
                <span className="text-[#bbcabf]">{runtime.policyDecision.reason}</span>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  )
}

function Field({
  field,
  value,
  onChange,
  models,
  currentProvider,
}: {
  field: ConfigField
  value: unknown
  onChange: (v: unknown) => void
  models?: ModelConfig[]
  currentProvider: string
}) {
  const inputCls =
    'w-full rounded-md border border-[#3c4a42] bg-[#09100c] px-3 py-2 text-[12px] font-mono text-[#dde4dd] outline-none transition-all focus:border-[#4edea3] focus:shadow-[0_0_0_2px_rgba(78,222,163,0.15)]'

  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] text-[#bbcabf]">{field.label}</span>

      {field.type === 'model-id' ? (
        <>
          <div className="relative">
            <select
              className={inputCls + ' appearance-none pr-7'}
              value={String(value ?? '')}
              onChange={(e) => onChange(e.target.value)}
              disabled={!models}
            >
              {!models && <option value="">Loading…</option>}
              {(models?.filter((m) => m.provider === currentProvider) ?? []).length === 0 && models && (
                <option value={String(value ?? '')}>{String(value ?? '—')}</option>
              )}
              {models
                ?.filter((m) => m.provider === currentProvider)
                .map((m) => (
                  <option key={m.id} value={m.id} disabled={!m.available}>
                    {m.label}{!m.available ? ' (no key)' : ''}
                  </option>
                ))}
            </select>
            <span className="material-symbols-outlined pointer-events-none absolute right-2 top-2 text-[#86948a]" style={{ fontSize: 16 }}>
              unfold_more
            </span>
          </div>
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </>
      ) : field.type === 'select' ? (
        <>
          <div className="relative">
            <select
              className={inputCls + ' appearance-none pr-7'}
              value={String(value ?? '')}
              onChange={(e) => onChange(e.target.value)}
            >
              {field.options?.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className="material-symbols-outlined pointer-events-none absolute right-2 top-2 text-[#86948a]" style={{ fontSize: 16 }}>
              unfold_more
            </span>
          </div>
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </>
      ) : field.type === 'text' ? (
        <>
          <textarea
            className={inputCls + ' resize-y'}
            rows={4}
            value={String(value ?? '')}
            placeholder={field.placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </>
      ) : field.type === 'string[]' ? (
        <>
          <textarea
            className={inputCls + ' resize-y'}
            rows={3}
            value={Array.isArray(value) ? value.join('\n') : ''}
            placeholder={field.placeholder}
            onChange={(e) =>
              onChange(
                e.target.value
                  .split('\n')
                  .map((line) => line.trim())
                  .filter((line) => line.length > 0),
              )
            }
          />
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">
              한 줄에 하나씩 입력. {field.description}
            </span>
          )}
        </>
      ) : field.type === 'boolean' ? (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            className="h-4 w-4 rounded border-[#3c4a42] bg-[#09100c] accent-[#4edea3]"
          />
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </div>
      ) : field.type === 'number' ? (
        <>
          <input
            type="number"
            className={inputCls}
            value={Number(value ?? 0)}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </>
      ) : (
        <>
          <input
            type="text"
            className={inputCls}
            value={String(value ?? '')}
            placeholder={field.placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
          {field.description && (
            <span className="font-mono text-[10px] text-[#86948a]">{field.description}</span>
          )}
        </>
      )}
    </label>
  )
}

function MetricCard({
  label,
  value,
  accent,
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className="flex flex-col gap-1 rounded border border-[#3c4a42]/60 bg-[#242c27] p-2">
      <span className="font-mono text-[10px] uppercase tracking-wider text-[#86948a]">{label}</span>
      <span
        className="font-mono text-[12px] text-[#dde4dd]"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </span>
    </div>
  )
}

type ReviewDeltaData = {
  per_criterion?: { id?: string; verdict?: string; evidence?: string }[]
  misalignments?: string[]
  elicit_questions?: string[]
} | null

type FinalResultData = {
  answer?: unknown
  /** output 노드 node_end.output의 리뷰 필드 */
  review?: ReviewDeltaData
  /** run_complete 결과의 리뷰 필드 */
  reviewDelta?: ReviewDeltaData
  reviewBranch?: string | null
} | null

/**
 * output 노드가 방출한 node_end.output({answer, review})을 우선 사용하고,
 * 아직 노드 이벤트가 없으면 run_complete로 받은 전역 runResult로 폴백한다.
 */
function pickFinalResult(
  lastOutput: unknown,
  runResult: Record<string, unknown> | null,
): FinalResultData {
  const fromNode =
    lastOutput && typeof lastOutput === 'object'
      ? (lastOutput as Record<string, unknown>)
      : null
  const src = fromNode && 'answer' in fromNode ? fromNode : runResult
  if (!src) return null
  return src as FinalResultData
}

function FinalResult({
  result,
  runStatus,
}: {
  result: FinalResultData
  runStatus: string
}) {
  if (!result || result.answer === undefined || result.answer === null) {
    return (
      <section className="flex flex-col gap-3">
        <h3 className="border-b border-[#3c4a42]/40 pb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
          Final Result
        </h3>
        <div className="rounded-md border border-dashed border-[#3c4a42] bg-[#09100c] p-4 text-center text-[11px] text-[#86948a]">
          {runStatus === 'running'
            ? '실행 중… 결과 대기 중'
            : '아직 결과가 없습니다. Run을 실행하세요.'}
        </div>
      </section>
    )
  }

  const review = result.review ?? result.reviewDelta
  const unmetCount =
    review?.per_criterion?.filter((v) => v.verdict === 'unmet').length ?? 0
  const misalignments = review?.misalignments ?? []
  const aligned = unmetCount === 0 && misalignments.length === 0
  const answerText =
    typeof result.answer === 'string'
      ? result.answer
      : JSON.stringify(result.answer, null, 2)

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-[#3c4a42]/40 pb-1">
        <h3 className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
          Final Result
        </h3>
        {review && (
          <span
            className="rounded px-1.5 py-0.5 font-mono text-[10px]"
            style={{
              color: aligned ? '#4edea3' : '#ff8a80',
              background: aligned ? '#4edea31a' : '#ff8a801a',
            }}
          >
            {aligned ? '✓ aligned' : `✗ ${unmetCount} unmet`}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[11px] text-[#86948a]">Answer</span>
          <button
            onClick={() => navigator.clipboard.writeText(answerText)}
            className="text-[#86948a] transition-colors hover:text-[#dde4dd]"
            title="Copy"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>content_copy</span>
          </button>
        </div>
        <div className="rounded-md border border-[#4edea3]/40 bg-[#0d1712] p-3">
          {typeof result.answer === 'string' ? (
            <Markdown>{answerText}</Markdown>
          ) : (
            <pre className="m-0 whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-[#dde4dd]">
              {answerText}
            </pre>
          )}
        </div>
      </div>

      {result.reviewBranch && (
        <div className="flex items-center gap-2 font-mono text-[11px] text-[#86948a]">
          <span>Review branch</span>
          <span className="text-[#bbcabf]">{result.reviewBranch}</span>
        </div>
      )}

      {misalignments.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[11px] text-[#86948a]">Misalignments</span>
          <div className="rounded-md border border-[#3c4a42] bg-[#09100c] p-2 text-[11px] leading-relaxed text-[#bbcabf]">
            {misalignments.map((m, i) => (
              <div key={i}>· {m}</div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function IOBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined) return null

  // output에 문자열 필드(answer/plan/reasoning 등)가 있으면 markdown 렌더,
  // 순수 구조체면 JSON 그대로 표시.
  const stringField = extractStringField(value)
  const copyText = stringField ?? JSON.stringify(value, null, 2)

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] text-[#86948a]">{label}</span>
        <button
          onClick={() => navigator.clipboard.writeText(copyText)}
          className="text-[#86948a] transition-colors hover:text-[#dde4dd]"
          title="Copy"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 13 }}>content_copy</span>
        </button>
      </div>
      <div className="rounded-md border border-[#3c4a42] bg-[#09100c] p-2 overflow-x-auto">
        {stringField ? (
          <Markdown>{stringField}</Markdown>
        ) : (
          <pre className="m-0 font-mono text-[11px] leading-relaxed text-[#dde4dd]">
            {JSON.stringify(value, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

/** output dict에서 대표 문자열 필드를 추출. 없으면 null. */
function extractStringField(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    for (const key of ['answer', 'plan', 'reasoning', 'summary', 'result']) {
      const v = obj[key]
      if (typeof v === 'string' && v.length > 0) return v
    }
  }
  return null
}

function statusColor(status: string) {
  switch (status) {
    case 'success': return '#4edea3'
    case 'failed':  return '#ff8a80'
    case 'running': return '#ffd180'
    case 'skipped': return '#86948a'
    default:        return '#bbcabf'
  }
}

const PROVIDERS = [
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'OpenAI',    value: 'openai'    },
  { label: 'Google',    value: 'google'    },
  { label: 'Local',     value: 'local'     },
] as const

const DEFAULT_MODELS: Record<string, string> = {
  anthropic: 'claude-haiku-4-5-20251001',
  openai:    'gpt-4o',
  google:    'gemini-3.5-flash',
  local:     'llama3',
}

let slotSeq = 0
const nextSlotId = () => `slot-${Date.now().toString(36)}-${slotSeq++}`

const SLOT_INPUT =
  'w-full rounded-md border border-[#3c4a42] bg-[#09100c] px-2 py-1.5 text-[11px] font-mono text-[#dde4dd] outline-none appearance-none focus:border-[#4edea3]'

// config.yaml execution 기본값 미러 — UI 표시용 (실제 해석은 백엔드에서)
const GLOBAL_NODE_TIMEOUT = 120
const GLOBAL_RETRY_DEFAULT = 1

function CollapsibleSection({ title, accent, children }: { title: string; accent: string; children: ReactNode }) {
  return (
    <details className="rounded-md border border-[#3c4a42]/60 bg-[#0c1310]">
      <summary className="flex cursor-pointer list-none select-none items-center gap-1.5 px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#86948a] [&::-webkit-details-marker]:hidden">
        <span className="material-symbols-outlined" style={{ fontSize: 12, color: accent }}>chevron_right</span>
        {title}
      </summary>
      <div className="flex flex-col gap-2 p-2.5 pt-1">{children}</div>
    </details>
  )
}

/** "상속 또는 override" 숫자 입력 — 비우면 모델/전역 기본값 상속, ↺ 로 되돌림. */
function InheritNumber({
  label, value, defaultLabel, min, max, step, onChange, description,
}: {
  label: string
  value: number | undefined
  defaultLabel: string
  min?: number; max?: number; step?: number
  onChange: (v: number | undefined) => void
  description?: string
}) {
  const isInherit = value === undefined || value === null
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] text-[#86948a]">{label}</span>
      <div className="relative">
        <input
          type="number"
          className={SLOT_INPUT + (isInherit ? ' text-[#5a665d]' : '')}
          min={min} max={max} step={step}
          placeholder={isInherit ? `Inherit (${defaultLabel})` : ''}
          value={isInherit ? '' : value}
          onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
        />
        {!isInherit && (
          <button
            type="button"
            onClick={() => onChange(undefined)}
            title="상속으로 되돌림"
            className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded text-[#86948a] hover:text-[#4edea3]"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 12 }}>restart_alt</span>
          </button>
        )}
      </div>
      {isInherit && description && (
        <span className="font-mono text-[9px] text-[#3c4a42]">{description}</span>
      )}
    </label>
  )
}

function FallbackEditor({
  value, models, onChange,
}: {
  value: ModelSlot['fallback']
  models?: ModelConfig[]
  onChange: (v: ModelSlot['fallback']) => void
}) {
  const enabled = !!value
  const provider = value?.provider ?? 'openai'
  const providerModels = models?.filter((m) => m.provider === provider) ?? []
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) =>
            onChange(e.target.checked ? { provider: 'openai', model: DEFAULT_MODELS['openai'] } : undefined)
          }
          className="h-3.5 w-3.5 rounded border-[#3c4a42] bg-[#09100c] accent-[#4edea3]"
        />
        <span className="text-[10px] text-[#86948a]">Fallback model 사용</span>
      </label>
      {enabled && value && (
        <div className="flex flex-col gap-1.5 pl-5">
          <div className="relative">
            <select
              className={SLOT_INPUT + ' pr-6'}
              value={provider}
              onChange={(e) => {
                const p = e.target.value as ModelSlot['provider']
                const pm = models?.filter((m) => m.provider === p) ?? []
                const fm = pm.find((m) => m.available)?.id ?? pm[0]?.id ?? DEFAULT_MODELS[p]
                onChange({ provider: p, model: fm })
              }}
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            <span className="material-symbols-outlined pointer-events-none absolute right-1.5 top-1.5 text-[#86948a]" style={{ fontSize: 14 }}>unfold_more</span>
          </div>
          <div className="relative">
            <select
              className={SLOT_INPUT + ' pr-6'}
              value={value.model}
              onChange={(e) => onChange({ ...value, model: e.target.value })}
              disabled={!models}
            >
              {providerModels.length === 0 && models && (
                <option value={value.model}>{value.model}</option>
              )}
              {providerModels.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.label}{!m.available ? ' (no key)' : ''}
                </option>
              ))}
            </select>
            <span className="material-symbols-outlined pointer-events-none absolute right-1.5 top-1.5 text-[#86948a]" style={{ fontSize: 14 }}>unfold_more</span>
          </div>
        </div>
      )}
    </div>
  )
}

function ModelSlotsEditor({
  slots,
  maxSlots,
  models,
  onChange,
  accent,
}: {
  slots: ModelSlot[]
  maxSlots: number
  models?: ModelConfig[]
  onChange: (slots: ModelSlot[]) => void
  accent: string
}) {
  const addSlot = () => {
    if (slots.length >= maxSlots) return
    const provider = 'google' as const
    const providerModels = models?.filter((m) => m.provider === provider) ?? []
    const firstModel = providerModels.find((m) => m.available)?.id ?? providerModels[0]?.id ?? DEFAULT_MODELS[provider]
    onChange([
      ...slots,
      { id: nextSlotId(), provider, model: firstModel, temperature: 0, role: '' },
    ])
  }

  const removeSlot = (id: string) => onChange(slots.filter((s) => s.id !== id))

  const updateSlot = (id: string, patch: Partial<ModelSlot>) =>
    onChange(slots.map((s) => (s.id === id ? { ...s, ...patch } : s)))

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-[#3c4a42]/40 pb-1">
        <h3 className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#4edea3]">
          Model Slots
        </h3>
        <span className="font-mono text-[10px]" style={{ color: accent }}>
          {slots.length} / {maxSlots}
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {slots.map((slot, idx) => {
          const providerModels = models?.filter((m) => m.provider === slot.provider) ?? []
          const modelCfg = models?.find((m) => m.id === slot.model)
          return (
            <div
              key={slot.id}
              className="flex flex-col gap-2 rounded-md border border-[#3c4a42] bg-[#09100c] p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] text-[#86948a]">Slot {idx + 1}</span>
                <button
                  onClick={() => removeSlot(slot.id)}
                  className="flex h-5 w-5 items-center justify-center rounded text-[#86948a] transition-colors hover:bg-[#ff8a80]/20 hover:text-[#ff8a80]"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 13 }}>close</span>
                </button>
              </div>

              {/* ── Identity ── */}
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[#86948a]">Role</span>
                <input
                  type="text"
                  className={SLOT_INPUT}
                  placeholder="e.g. Primary Reasoning"
                  value={slot.role}
                  onChange={(e) => updateSlot(slot.id, { role: e.target.value })}
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[#86948a]">Provider</span>
                <div className="relative">
                  <select
                    className={SLOT_INPUT + ' pr-6'}
                    value={slot.provider}
                    onChange={(e) => {
                      const provider = e.target.value as ModelSlot['provider']
                      const providerModels = models?.filter((m) => m.provider === provider) ?? []
                      const firstModel = providerModels.find((m) => m.available)?.id ?? providerModels[0]?.id ?? DEFAULT_MODELS[provider]
                      updateSlot(slot.id, { provider, model: firstModel })
                    }}
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined pointer-events-none absolute right-1.5 top-1.5 text-[#86948a]" style={{ fontSize: 14 }}>unfold_more</span>
                </div>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[#86948a]">Model</span>
                <div className="relative">
                  <select
                    className={SLOT_INPUT + ' pr-6'}
                    value={slot.model}
                    onChange={(e) => updateSlot(slot.id, { model: e.target.value })}
                    disabled={!models}
                  >
                    {!models && <option value="">Loading…</option>}
                    {providerModels.length === 0 && models && (
                      <option value={slot.model}>{slot.model}</option>
                    )}
                    {providerModels.map((m) => (
                      <option key={m.id} value={m.id} disabled={!m.available}>
                        {m.label}{!m.available ? ' (no key)' : ''}
                      </option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined pointer-events-none absolute right-1.5 top-1.5 text-[#86948a]" style={{ fontSize: 14 }}>unfold_more</span>
                </div>
              </label>

              {/* ── Generation ── */}
              <label className="flex flex-col gap-1">
                <span className="text-[10px] text-[#86948a]">Temperature</span>
                <input
                  type="number"
                  className={SLOT_INPUT}
                  min={0}
                  max={2}
                  step={0.1}
                  value={slot.temperature}
                  onChange={(e) => updateSlot(slot.id, { temperature: Number(e.target.value) })}
                />
              </label>

              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-[#86948a]">Max output tokens</span>
                <div className="flex gap-1">
                  {([
                    ['Short', 512],
                    ['Default', undefined],
                    ['Long', 8192],
                  ] as const).map(([lbl, val]) => {
                    const active =
                      val === undefined ? slot.maxTokens === undefined : slot.maxTokens === val
                    return (
                      <button
                        key={lbl}
                        type="button"
                        onClick={() => updateSlot(slot.id, { maxTokens: val })}
                        className={
                          'flex-1 rounded border px-1.5 py-1 font-mono text-[10px] transition-colors ' +
                          (active
                            ? 'border-[#4edea3]/60 bg-[#4edea3]/10 text-[#4edea3]'
                            : 'border-[#3c4a42] text-[#86948a] hover:border-[#4edea3]/40')
                        }
                      >
                        {lbl}
                      </button>
                    )
                  })}
                </div>
                <InheritNumber
                  label="또는 직접 입력"
                  value={slot.maxTokens}
                  defaultLabel={modelCfg?.maxTokens ? String(modelCfg.maxTokens) : 'model default'}
                  min={1}
                  step={1}
                  onChange={(v) => updateSlot(slot.id, { maxTokens: v })}
                  description="비우면 모델 기본값(config.yaml) 상속"
                />
              </div>

              {/* ── Advanced (생성) ── */}
              <CollapsibleSection title="Advanced" accent={accent}>
                <InheritNumber
                  label="Top P"
                  value={slot.topP}
                  defaultLabel="model default"
                  min={0}
                  max={1}
                  step={0.05}
                  onChange={(v) => updateSlot(slot.id, { topP: v })}
                  description="일반적으로 Temperature 또는 Top P 중 하나만 조절"
                />
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] text-[#86948a]">Stop sequences</span>
                  <textarea
                    className={SLOT_INPUT + ' resize-y'}
                    rows={2}
                    placeholder="한 줄에 하나"
                    value={(slot.stopSequences ?? []).join('\n')}
                    onChange={(e) =>
                      updateSlot(slot.id, {
                        stopSequences: e.target.value
                          .split('\n')
                          .map((s) => s.trim())
                          .filter((s) => s.length > 0),
                      })
                    }
                  />
                  <span className="font-mono text-[9px] text-[#3c4a42]">
                    이 문자열이 나오면 생성 중단. 빈 줄은 무시됨.
                  </span>
                </label>
                {(slot.provider === 'openai' || slot.provider === 'local') && (
                  <InheritNumber
                    label="Seed"
                    value={slot.seed}
                    defaultLabel="—"
                    step={1}
                    onChange={(v) => updateSlot(slot.id, { seed: v })}
                    description="재현성 보조 — 완전 결정론을 보장하지는 않음"
                  />
                )}
              </CollapsibleSection>

              {/* ── Reliability (운영) ── */}
              <CollapsibleSection title="Reliability" accent={accent}>
                <InheritNumber
                  label="Timeout (초)"
                  value={slot.timeoutSeconds}
                  defaultLabel={`${GLOBAL_NODE_TIMEOUT}s`}
                  min={1}
                  max={600}
                  step={1}
                  onChange={(v) => updateSlot(slot.id, { timeoutSeconds: v })}
                  description="이 노드 LLM 호출의 최대 대기 시간"
                />
                <InheritNumber
                  label="Retry count"
                  value={slot.retryCount}
                  defaultLabel={String(GLOBAL_RETRY_DEFAULT)}
                  min={0}
                  max={10}
                  step={1}
                  onChange={(v) => updateSlot(slot.id, { retryCount: v })}
                  description="타임아웃/일시오류/출력검증 실패 시 추가 재시도"
                />
                <FallbackEditor
                  value={slot.fallback}
                  models={models}
                  onChange={(v) => updateSlot(slot.id, { fallback: v ?? undefined })}
                />
              </CollapsibleSection>
            </div>
          )
        })}

        {slots.length < maxSlots && (
          <button
            onClick={addSlot}
            className="flex items-center justify-center gap-1.5 rounded-md border border-dashed border-[#3c4a42] py-2 text-[11px] text-[#86948a] transition-colors hover:border-[#4edea3]/60 hover:text-[#4edea3]"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add</span>
            Add Model Slot
          </button>
        )}
      </div>
    </section>
  )
}
