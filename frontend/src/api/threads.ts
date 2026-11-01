import client from './client'
import type { PaginatedResponse, Thread, ThreadWithItems, ThreadRecomputeAccepted, ThreadRecomputeStatus, ThreadDigestResult } from '../types'
export interface ThreadsQuery {
  task_id?: string
  page?: number
  per_page?: number
  sort?: 'first_seen' | 'hotness'
}

export const threadsApi = {
  list: (params?: ThreadsQuery) =>
    client.get<PaginatedResponse<Thread>>('/items/threads', { params }).then((r) => r.data),

  get: (threadId: string) =>
    client.get<ThreadWithItems>(`/items/threads/${threadId}`).then((r) => r.data),

  /** 重建全部 Thread（后台执行，返回 202；进度经 recomputeStatus 轮询） */
  recompute: (windowHours: number = 24) =>
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
