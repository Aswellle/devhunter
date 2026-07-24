import client from './client'
import type { PaginatedResponse, SourceTemplate, Task, TaskCreate, TaskExecution, TaskUpdate } from '../types'

export const tasksApi = {
  list: (params?: { status?: string; page?: number; per_page?: number }) =>
    client.get<PaginatedResponse<Task>>('/tasks', { params }).then((r) => r.data),

  get: (id: string) =>
    client.get<Task>(`/tasks/${id}`).then((r) => r.data),

  create: (data: TaskCreate) =>
    client.post<Task>('/tasks', data).then((r) => r.data),

  update: (id: string, data: TaskUpdate) =>
    client.put<Task>(`/tasks/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    client.delete(`/tasks/${id}`),

  execute: (id: string) =>
    client.post<{ execution_id: string; message: string }>(`/tasks/${id}/execute`).then((r) => r.data),

  templates: () =>
    client.get<SourceTemplate[]>('/tasks/templates').then((r) => r.data),

  executions: (id: string, params?: { page?: number; per_page?: number }) =>
    client.get<PaginatedResponse<TaskExecution>>(`/tasks/${id}/executions`, { params }).then((r) => r.data),
}
