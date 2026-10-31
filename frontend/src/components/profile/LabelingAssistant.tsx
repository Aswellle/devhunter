/**
 * LabelingAssistant：推荐质量打标助手（金标采样）。
 *
 * 对采样条目逐条判断"感兴趣 / 不感兴趣"，用于评估推荐排序质量
 * （排序贴合度 = 正例得分高于负例的比例）。打标只用于评估，
 * 不影响推荐结果与画像。
 *
 * 队列中刻意不展示模型对候选项的打分：标注者先于模型判断，
 * 贴合度才反映排序质量而非"与模型的一致度"。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { ClipboardList, ThumbsDown, ThumbsUp } from 'lucide-react'
import type { LabelSampleItem } from '../../types'
import { userPrefsApi } from '../../api/user_prefs'
import { queryKeys } from '../../api/queryKeys'
import { errorMessage } from '../../api/client'
import { isSafeExternalUrl } from '../../utils/url'
import { ClampText } from '../ui/ClampText'

function LabelRow({
  item,
  onLabel,
  pending,
}: {
  item: LabelSampleItem
  onLabel: (item: LabelSampleItem, label: boolean) => void
  pending: boolean
}) {
  return (
    <div className="flex items-start gap-3 py-3">
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-400 mb-0.5">{item.task_name ?? '未知来源'}</div>
        {/* 爬取来源的 URL 不受信：非 http(s) 协议降级为纯文本，防 javascript: 注入 */}
        {isSafeExternalUrl(item.url) ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-gray-800 hover:text-primary-600 transition-colors"
          >
            {item.title}
          </a>
        ) : (
          <span className="text-sm font-medium text-gray-800">{item.title}</span>
        )}
        <ClampText text={item.summary ?? undefined} className="text-xs text-gray-500 mt-0.5" />
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          disabled={pending}
          onClick={() => onLabel(item, true)}
          className="btn-ghost btn-sm text-emerald-700 hover:bg-emerald-50"
          title="这条内容符合我的兴趣"
        >
          <ThumbsUp className="h-3.5 w-3.5" aria-hidden="true" />
          感兴趣
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => onLabel(item, false)}
          className="btn-ghost btn-sm text-gray-500 hover:bg-gray-100"
          title="对这类内容不感兴趣"
        >
          <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
          不感兴趣
        </button>
      </div>
    </div>
  )
}

export function LabelingAssistant() {
  const qc = useQueryClient()
  // 本批已标注的条目（仅在渲染期过滤队列，避免 effect 同步 state）
  const [labeledHere, setLabeledHere] = useState<ReadonlySet<string>>(new Set())

  const { data: sample, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: queryKeys.userPrefs.labelSample(),
    queryFn: () => userPrefsApi.getLabelSample(),
  })

  const { data: summary } = useQuery({
    queryKey: queryKeys.userPrefs.labelSummary(),
    queryFn: () => userPrefsApi.getLabelSummary(),
  })

  const labelMutation = useMutation({
    mutationFn: (payload: { item_id: string; label: boolean }) =>
      userPrefsApi.submitLabel(payload),
    onSuccess: (_, payload) => {
      setLabeledHere((prev) => new Set(prev).add(payload.item_id))
      qc.invalidateQueries({ queryKey: queryKeys.userPrefs.labelSummary() })
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '标注保存失败')),
  })

  const handleLabel = (item: LabelSampleItem, label: boolean) => {
    labelMutation.mutate({ item_id: item.id, label })
  }

  const handleRefresh = () => {
    // 先等新一批数据落定再清本地已标集合——立即清空会让旧缓存里的
    // 已标条目在刷新间隙闪现回队列（重复提交无害，观感差）
    refetch().then(() => setLabeledHere(new Set()))
  }

  const remaining = (sample ?? []).filter((it) => !labeledHere.has(it.id))
  const batchDone = !isLoading && (sample?.length ?? 0) > 0 && remaining.length === 0

  const winRateText =
    summary?.win_rate != null
      ? `${Math.round(summary.win_rate * 100)}%`
      : null

  return (
    <section className="card p-4">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <ClipboardList className="h-5 w-5 text-gray-400" aria-hidden="true" />
          推荐质量打标
        </h2>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isFetching}
          className="btn-ghost btn-sm text-gray-500"
        >
          {isFetching ? '刷新中…' : '换一批'}
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        对随机抽样的推荐候选标注"是否感兴趣"，用于评估推荐排序质量；
        标注只用于评估，不会改变你的推荐结果。
        {summary && summary.total > 0 && (
          <>
            {' '}已标 <b className="text-gray-700">{summary.total}</b> 条
            （感兴趣 {summary.positive} / 不感兴趣 {summary.negative}）
            {winRateText != null ? (
              <>，排序贴合度 <b className="text-gray-700">{winRateText}</b></>
            ) : (
              <>，感兴趣与不感兴趣各至少 1 条后可计算贴合度</>
            )}
          </>
        )}
      </p>

      {isLoading ? (
        <p className="text-sm text-gray-400 py-4 text-center">加载候选中…</p>
      ) : isError ? (
        <div className="text-sm text-gray-500 py-3">
          加载失败
          <button type="button" onClick={() => refetch()} className="ml-2 text-primary-600 hover:underline">
            重试
          </button>
        </div>
      ) : remaining.length > 0 ? (
        <div className="divide-y divide-gray-100">
          {remaining.map((item) => (
            <LabelRow
              key={item.id}
              item={item}
              onLabel={handleLabel}
              pending={labelMutation.isPending}
            />
          ))}
        </div>
      ) : batchDone ? (
        <div className="text-sm text-gray-500 py-4 text-center">
          本批 {sample?.length} 条已全部标注
          <button type="button" onClick={handleRefresh} className="ml-2 text-primary-600 hover:underline">
            换一批
          </button>
        </div>
      ) : (
        <p className="text-sm text-gray-400 py-4 text-center">
          暂无可标注的候选（最近 7 天没有新采集内容，或已全部标注）
        </p>
      )}
    </section>
  )
}
