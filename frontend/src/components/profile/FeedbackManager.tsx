/**
 * FeedbackManager：负反馈屏蔽管理（工作流 D：反馈可撤销）。
 *
 * 列出用户点过「不感兴趣」的条目、屏蔽的来源、静音的主题，支持逐条
 * 撤销——撤销即删除反馈行，推荐候选立即恢复（服务端同一事务语义）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Undo2, Loader2 } from 'lucide-react'
import { userPrefsApi } from '../../api/user_prefs'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { Empty } from '../ui/Empty'
import type { NegativeFeedbackEntry } from '../../types'

const TYPE_LABELS: Record<NegativeFeedbackEntry['feedback_type'], string> = {
  not_interested: '不感兴趣（条目）',
  hide_source: '屏蔽来源',
  mute_topic: '静音主题',
}

export function FeedbackManager() {
  const qc = useQueryClient()
  const listQuery = useQuery({
    queryKey: queryKeys.userPrefs.negativeFeedback(),
    queryFn: () => userPrefsApi.listFeedback(),
  })

  const revokeMutation = useMutation({
    mutationFn: (id: string) => userPrefsApi.revokeFeedback(id),
    onSuccess: () => {
      toast.success('已撤销屏蔽，内容恢复推荐')
      qc.invalidateQueries({ queryKey: queryKeys.userPrefs.negativeFeedback() })
      qc.invalidateQueries({ queryKey: queryKeys.recommendations.all })
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '撤销失败')),
  })

  const rows = listQuery.data ?? []

  return (
    <section aria-label="屏蔽管理" className="mb-6">
      <h2 className="text-base font-semibold text-primary mb-2">屏蔽管理</h2>
      <p className="text-sm text-gray-500 mb-3">
        「不感兴趣」的条目、屏蔽的来源与静音的主题都会在此列出；撤销后立即恢复推荐。
      </p>

      {listQuery.isLoading && (
        <div className="flex justify-center py-6" role="status" aria-live="polite">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}

      {!listQuery.isLoading && rows.length === 0 && (
        <Empty title="暂无屏蔽记录" description="在「为你推荐」里点「不感兴趣」后，可在这里撤销。" />
      )}

      {rows.length > 0 && (
        <ul className="border rounded-lg divide-y divide-gray-100">
          {rows.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded">
                    {TYPE_LABELS[row.feedback_type] ?? row.feedback_type}
                  </span>
                  <span className="text-sm truncate">{row.target_value}</span>
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {row.created_at}
                  {row.reason ? ` · ${row.reason}` : ''}
                </div>
              </div>
              <button
                onClick={() => revokeMutation.mutate(row.id)}
                disabled={revokeMutation.isPending}
                aria-label={`撤销屏蔽：${row.target_value}`}
                className="btn-ghost flex items-center gap-1 px-2.5 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 shrink-0"
              >
                {revokeMutation.isPending
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Undo2 className="h-3.5 w-3.5" />}
                撤销
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
