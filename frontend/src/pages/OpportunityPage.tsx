/**
 * OpportunityPage：机会板（PROD-005）。
 *
 * 把值得跟进的条目/事件收进 Inbox，按状态流转（inbox → investigating →
 * planned → building → shipped / dismissed），写笔记、标签与提醒时间；
 * 每条机会都能点回原始证据。
 *
 * 创建入口：从条目卡/热点卡的「加入机会板」跳转带 ?item= / ?thread=，
 * 本页展示预填的来源并允许补充类型/优先级。
 */
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Lightbulb, ExternalLink, Loader2, Plus, AlertCircle } from 'lucide-react'
import { opportunitiesApi } from '../api/opportunities'
import { queryKeys } from '../api/queryKeys'
import { errorMessage } from '../api/client'
import { Empty } from '../components/ui/Empty'
import { Spinner } from '../components/ui/Spinner'
import type { Opportunity, OpportunityStatus, OpportunityType } from '../types'

const STATUS_LABELS: Record<OpportunityStatus, string> = {
  inbox: '收件箱',
  investigating: '调研中',
  planned: '已计划',
  building: '进行中',
  shipped: '已交付',
  dismissed: '已忽略',
}

const STATUS_ORDER: OpportunityStatus[] = [
  'inbox', 'investigating', 'planned', 'building', 'shipped', 'dismissed',
]

const TYPE_LABELS: Record<OpportunityType, string> = {
  user_problem: '用户痛点',
  product_launch: '产品发布',
  open_source_project: '开源项目',
  hiring: '招聘',
  collaboration: '合作',
  trend: '趋势',
  technical_risk: '技术风险',
  idea: '灵感',
}

const PRIORITY_LABELS = { low: '低', normal: '中', high: '高' } as const

export function OpportunityPage() {
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const originItem = params.get('item')
  const originThread = params.get('thread')
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | ''>('')
  const [draftNotes, setDraftNotes] = useState<Record<string, string>>({})

  const listQuery = useQuery({
    queryKey: queryKeys.opportunities.list(statusFilter || undefined),
    queryFn: () => opportunitiesApi.list(statusFilter || undefined),
  })

  const createMutation = useMutation({
    mutationFn: () => opportunitiesApi.create({
      origin_type: originItem ? 'item' : 'thread',
      origin_id: originItem || originThread || '',
    }),
    onSuccess: (created) => {
      toast.success('已加入机会板')
      qc.invalidateQueries({ queryKey: queryKeys.opportunities.all })
      // 清掉来源参数避免重复创建
      setParams({}, { replace: true })
      setDraftNotes((prev) => ({ ...prev, [created.id]: created.notes }))
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '加入机会板失败')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Parameters<typeof opportunitiesApi.update>[1] }) =>
      opportunitiesApi.update(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.opportunities.all })
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '更新失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => opportunitiesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.opportunities.all }),
    onError: (e: unknown) => toast.error(errorMessage(e, '删除失败')),
  })

  const grouped = useMemo(() => {
    const map = new Map<OpportunityStatus, Opportunity[]>()
    for (const opp of listQuery.data ?? []) {
      const arr = map.get(opp.status) ?? []
      arr.push(opp)
      map.set(opp.status, arr)
    }
    return map
  }, [listQuery.data])

  const visibleStatuses = statusFilter
    ? STATUS_ORDER.filter((s) => s === statusFilter)
    : STATUS_ORDER

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Lightbulb className="h-5 w-5 text-amber-500" />
          机会板
        </h1>
        {originItem || originThread ? (
          <button
            onClick={() => createMutation.mutate()}
            disabled={createMutation.isPending}
            className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-sm"
          >
            {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            把{originItem ? '该条目' : '该热点'}加入机会板
          </button>
        ) : (
          <p className="text-sm text-gray-500">
            在条目或热点卡片上点「加入机会板」开始追踪
          </p>
        )}
      </div>

      {/* 状态筛选 */}
      <div role="tablist" aria-label="机会状态筛选" className="flex gap-1 mb-5 border-b border-gray-200 flex-wrap">
        <button
          role="tab"
          aria-selected={statusFilter === ''}
          onClick={() => setStatusFilter('')}
          className={`px-3 py-2 text-sm border-b-2 ${statusFilter === '' ? 'border-blue-600 text-blue-700 font-medium' : 'border-transparent text-gray-500'}`}
        >
          全部
        </button>
        {STATUS_ORDER.map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={statusFilter === s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-2 text-sm border-b-2 ${statusFilter === s ? 'border-blue-600 text-blue-700 font-medium' : 'border-transparent text-gray-500'}`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {listQuery.isLoading && <div className="flex justify-center py-16"><Spinner /></div>}

      {!listQuery.isLoading && (listQuery.data?.length ?? 0) === 0 && (
        <Empty
          title="还没有机会"
          description="把值得跟进的条目或热点加进来，按收件箱 → 调研 → 计划 → 进行 → 交付推进。"
        />
      )}

      <div className="space-y-6">
        {visibleStatuses.map((status) => {
          const opps = grouped.get(status) ?? []
          if (opps.length === 0) return null
          return (
            <section key={status} aria-label={STATUS_LABELS[status]}>
              <h2 className="text-sm font-medium text-gray-600 mb-2">
                {STATUS_LABELS[status]}（{opps.length}）
              </h2>
              <div className="space-y-2">
                {opps.map((opp) => (
                  <article key={opp.id} className="border rounded-lg p-4 bg-surface">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="font-medium truncate">{opp.title}</h3>
                        <div className="flex items-center gap-2 mt-1 text-xs text-gray-500 flex-wrap">
                          <span className="px-1.5 py-0.5 bg-gray-100 rounded">
                            {TYPE_LABELS[opp.opportunity_type]}
                          </span>
                          <span className={`px-1.5 py-0.5 rounded ${
                            opp.priority === 'high' ? 'bg-red-50 text-red-700'
                              : opp.priority === 'low' ? 'bg-gray-100 text-gray-600'
                                : 'bg-blue-50 text-blue-700'
                          }`}>
                            优先级 {PRIORITY_LABELS[opp.priority]}
                          </span>
                          <a
                            href={opp.evidence?.url || '#'}
                            target={opp.evidence?.type === 'item' ? '_blank' : undefined}
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                          >
                            <ExternalLink className="h-3 w-3" />
                            原始证据
                          </a>
                          {opp.evidence_missing && (
                            <span className="inline-flex items-center gap-1 text-amber-700">
                              <AlertCircle className="h-3 w-3" />
                              原始证据已失效（来源可能已按 TTL 清理）
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <label className="sr-only" htmlFor={`status-${opp.id}`}>状态</label>
                        <select
                          id={`status-${opp.id}`}
                          value={opp.status}
                          onChange={(e) => updateMutation.mutate({
                            id: opp.id,
                            patch: { status: e.target.value as OpportunityStatus },
                          })}
                          className="text-sm border rounded px-2 py-1"
                        >
                          {STATUS_ORDER.map((s) => (
                            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => deleteMutation.mutate(opp.id)}
                          className="text-xs text-gray-400 hover:text-danger px-2 py-1"
                        >
                          删除
                        </button>
                      </div>
                    </div>

                    <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
                      <div>
                        <label className="sr-only" htmlFor={`notes-${opp.id}`}>笔记</label>
                        <textarea
                          id={`notes-${opp.id}`}
                          rows={2}
                          value={draftNotes[opp.id] ?? opp.notes}
                          onChange={(e) => setDraftNotes((prev) => ({ ...prev, [opp.id]: e.target.value }))}
                          onBlur={() => {
                            const value = draftNotes[opp.id]
                            if (value !== undefined && value !== opp.notes) {
                              updateMutation.mutate({ id: opp.id, patch: { notes: value } })
                            }
                          }}
                          placeholder="笔记：用户原话、验证计划、下一步…"
                          className="w-full text-sm border rounded px-2 py-1.5"
                        />
                      </div>
                      <div className="flex flex-col gap-1 text-xs">
                        <label className="text-gray-500" htmlFor={`remind-${opp.id}`}>提醒时间</label>
                        <input
                          id={`remind-${opp.id}`}
                          type="datetime-local"
                          defaultValue={opp.remind_at ? opp.remind_at.slice(0, 16) : ''}
                          onBlur={(e) => {
                            const v = e.target.value
                            updateMutation.mutate({
                              id: opp.id,
                              patch: { remind_at: v ? `${v}:00Z` : null },
                            })
                          }}
                          className="border rounded px-2 py-1"
                        />
                        <label className="text-gray-500 mt-1" htmlFor={`tags-${opp.id}`}>标签（逗号分隔）</label>
                        <input
                          id={`tags-${opp.id}`}
                          type="text"
                          defaultValue={opp.tags.join(', ')}
                          onBlur={(e) => {
                            const tags = e.target.value.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
                            updateMutation.mutate({ id: opp.id, patch: { tags } })
                          }}
                          className="border rounded px-2 py-1"
                        />
                      </div>
                    </div>

                    {opp.events.length > 0 && (
                      <details className="mt-2 text-xs text-gray-500">
                        <summary className="cursor-pointer select-none">审计记录（{opp.events.length}）</summary>
                        <ul className="mt-1 space-y-0.5">
                          {opp.events.map((evt) => (
                            <li key={evt.id}>
                              {evt.created_at} · {evt.event_type}
                              {evt.from_value || evt.to_value
                                ? ` · ${evt.from_value ?? ''} → ${evt.to_value ?? ''}`
                                : ''}
                              {evt.note ? ` · ${evt.note}` : ''}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
