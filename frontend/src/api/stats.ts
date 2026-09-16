import client from './client'

export interface StatsData {
  total_items: number
  items_today: number
  executions_today: number
  tasks: { active: number; paused: number; error: number; total: number }
  success_rate_7d: number | null
  total_executions_7d: number
  failures_7d: number
  daily_items: { date: string; count: number }[]
  top_tasks_7d: { id: string; name: string; item_count: number }[]
}

export const statsApi = {
  get: () => client.get<StatsData>('/stats').then((r) => r.data),
}
