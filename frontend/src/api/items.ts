import client from './client'
import type { Item, PaginatedResponse } from '../types'

export interface ItemsQuery {
  task_id?: string
  search?: string
  starred?: boolean
  is_read?: boolean
  page?: number
  per_page?: number
}

export const itemsApi = {
  list: (params?: ItemsQuery) =>
    client.get<PaginatedResponse<Item>>('/items', { params }).then((r) => r.data),

  patch: (id: string, data: { is_read?: boolean; is_starred?: boolean }) =>
    client.patch<Item>(`/items/${id}`, data).then((r) => r.data),

  batchPatch: (ids: string[], data: { is_read?: boolean; is_starred?: boolean }) =>
    client.patch<{ updated: number }>('/items/batch', { ids, ...data }).then((r) => r.data),

  batchDelete: (ids: string[]) =>
    client.post<{ deleted: number }>('/items/batch-delete', { ids }).then((r) => r.data),
}
