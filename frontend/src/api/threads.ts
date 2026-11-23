import client from './client'
import type {
  PaginatedResponse,
  Thread,
  ThreadAggregatePayload,
  ThreadAggregationOverview,
  ThreadConsolidateResult,
  ThreadDigestResult,
  ThreadRecomputeAccepted,
  ThreadRecomputeStatus,
  ThreadWithItems,
} from '../types'

export interface ThreadsQuery {
  task_id?: string
  page?: number
  per_page?: number
  sort?: 'first_seen' | 'hotness'
  /** 最小报道数：2 = 只看多来源热点 */
  min_items?: number
}

export const threadsApi = {
  list: (params?: ThreadsQuery) =>
    client.get<PaginatedResponse<Thread>>('/items/threads', { params }).then((r) => r.data),

  get: (threadId: string) =>
    client.get<ThreadWithItems>(`/items/threads/${threadId}`).then((r) => r.data),

  /** 聚合概览：来源数、多来源/单条 Thread、待补聚条目、最近合并结果 */
  overview: (windowHours: number = 72) =>
    client
      .get<ThreadAggregationOverview>('/items/threads/overview', {
        params: { window_hours: windowHours },
      })
      .then((r) => r.data),

  /** 立即聚合（增量）：补聚孤儿 + 合并可归并的单条 Thread，不删除历史 */
  consolidate: (windowHours: number = 72) =>
    client
      .post<ThreadConsolidateResult>('/items/threads/consolidate', {
        window_hours: windowHours,
      })
      .then((r) => r.data),

  /** 手动聚合：把勾选条目收进新热点或既有热点 */
  aggregate: (payload: ThreadAggregatePayload) =>
    client.post<ThreadWithItems>('/items/threads/aggregate', payload).then((r) => r.data),

  /** 重建全部 Thread（后台执行，返回 202；进度经 recomputeStatus 轮询） */
  recompute: (windowHours: number = 72) =>
    client
      .post<ThreadRecomputeAccepted>('/items/threads/recompute', { window_hours: windowHours })
      .then((r) => r.data),

  /** 查询后台重建状态 */
  recomputeStatus: () =>
    client.get<ThreadRecomputeStatus>('/items/threads/recompute/status').then((r) => r.data),

  /** 手动生成/更新 AI 综述（force=True 重新生成；相同材料命中结果复用不重复付费） */
  generateDigest: (threadId: string, force: boolean = false) =>
    client
      .post<ThreadDigestResult>(`/items/threads/${threadId}/digest`, { force })
      .then((r) => r.data),

  /** 解除一条"同一故事线"关联（拆除误关联） */
  unlinkRelation: (threadId: string, relatedThreadId: string) =>
    client.delete(`/items/threads/${threadId}/relations/${relatedThreadId}`),
}
