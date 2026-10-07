import client from './client'
import type { PaginatedResponse, Thread, ThreadWithItems, ThreadRecomputeResult } from '../types'

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

  /** 重建全部 Thread（同步执行；窗口小时数控制候选活动范围） */
  recompute: (windowHours: number = 24) =>
    client
      .post<ThreadRecomputeResult>('/items/threads/recompute', { window_hours: windowHours })
      .then((r) => r.data),
}
