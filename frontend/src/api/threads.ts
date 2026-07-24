import client from './client'
import type { PaginatedResponse, Thread, ThreadWithItems } from '../types'

export interface ThreadsQuery {
  task_id?: string
  page?: number
  per_page?: number
}

export const threadsApi = {
  list: (params?: ThreadsQuery) =>
    client.get<PaginatedResponse<Thread>>('/items/threads', { params }).then((r) => r.data),

  get: (threadId: string) =>
    client.get<ThreadWithItems>(`/items/threads/${threadId}`).then((r) => r.data),
}
