import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  loadOpenRouterCatalog,
  loadOpenRouterFavorites,
  saveOpenRouterFavorites,
} from '@/registry/loadOpenRouterCatalog'

/**
 * OpenRouter는 모델이 수백 개라 노드 UI(Inspector 모델 슬롯)에 전부 노출할 수 없다.
 * 여기서 라이브 카탈로그를 검색해 즐겨찾기 몇 개만 고르면, /api/models가 그것만
 * openrouter 모델로 내려준다 (server/main.py:_load_models_config).
 */
export function OpenRouterFavoritesModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const { data: catalog, isLoading: catalogLoading, isError: catalogError, refetch } = useQuery({
    queryKey: ['openrouter-catalog'],
    queryFn: loadOpenRouterCatalog,
    enabled: open,
    staleTime: 60_000,
    retry: 1,
  })

  const { data: favorites } = useQuery({
    queryKey: ['openrouter-favorites'],
    queryFn: loadOpenRouterFavorites,
    enabled: open,
  })

  useEffect(() => {
    if (favorites) setDraft(new Set(favorites))
  }, [favorites])

  if (!open) return null

  const toggle = (id: string) =>
    setDraft((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const filtered =
    query.trim().length === 0
      ? catalog
      : catalog?.filter(
          (m) =>
            m.id.toLowerCase().includes(query.toLowerCase()) ||
            m.label.toLowerCase().includes(query.toLowerCase()),
        )

  const handleSave = async () => {
    setSaving(true)
    try {
      await saveOpenRouterFavorites([...draft])
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['openrouter-favorites'] })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6">
      <div className="flex h-[80vh] w-[560px] flex-col rounded-lg border border-[#3c4a42] bg-[#1a211d] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#3c4a42] px-4 py-3">
          <div className="flex flex-col">
            <h2 className="text-[13px] font-semibold text-[#dde4dd]">OpenRouter Favorites</h2>
            <span className="text-[10px] text-[#86948a]">
              선택한 모델만 노드 모델 슬롯에 표시됩니다 ({draft.size}개 선택됨)
            </span>
          </div>
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded text-[#86948a] transition-colors hover:bg-[#242c27] hover:text-[#dde4dd]"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
          </button>
        </div>

        <div className="px-4 pt-3">
          <input
            type="text"
            autoFocus
            placeholder="모델 id나 이름으로 검색…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded border border-[#3c4a42] bg-[#09100c] px-3 py-2 text-[12px] text-[#dde4dd] outline-none transition-colors focus:border-[#4edea3]"
          />
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {catalogLoading && (
            <p className="text-[11px] text-[#86948a]">카탈로그 불러오는 중…</p>
          )}
          {catalogError && (
            <div className="flex flex-col items-start gap-2 text-[11px] text-[#ff8a80]">
              <span>OpenRouter 카탈로그를 불러오지 못했습니다.</span>
              <button
                onClick={() => refetch()}
                className="rounded border border-[#ff8a80]/40 px-2 py-1 text-[10px] hover:bg-[#ff8a80]/10"
              >
                다시 시도
              </button>
            </div>
          )}
          {filtered && filtered.length === 0 && (
            <p className="text-[11px] text-[#86948a]">검색 결과 없음</p>
          )}
          <ul className="flex flex-col gap-1">
            {filtered?.map((m) => (
              <li key={m.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 hover:bg-[#242c27]">
                  <input
                    type="checkbox"
                    checked={draft.has(m.id)}
                    onChange={() => toggle(m.id)}
                    className="mt-0.5"
                  />
                  <div className="flex flex-col">
                    <span className="font-mono text-[11px] text-[#dde4dd]">{m.label}</span>
                    <span className="font-mono text-[9px] text-[#86948a]">{m.id}</span>
                  </div>
                </label>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#3c4a42] px-4 py-3">
          <button
            onClick={onClose}
            className="rounded px-3 py-1.5 text-[12px] text-[#86948a] transition-colors hover:text-[#dde4dd]"
          >
            취소
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-[#4edea3] px-4 py-1.5 text-[12px] font-bold text-[#003824] transition-colors hover:bg-[#6ffbbe] disabled:opacity-50"
          >
            {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}
