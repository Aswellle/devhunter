/**
 * Thread 生命周期状态推导（纯函数）。
 *
 * 三态语义：近期活跃 / 观察中 / 历史事件。
 * 规则由最近一条报道时间推导，无需后端新增字段：
 * - 24h 内有更新 → 近期活跃（刚有报道加入）
 * - 72h 内有更新 → 观察中（可能还在发展）
 * - 其余 → 历史事件（冷却）
 *
 * 注意：这是"最近一条报道的时间"，不是"正在抓取"——聚合在每次采集后
 * 与每小时定时执行，只有新报道加入才会改变这里的状态。
 */

export type ThreadStatus = 'active' | 'watching' | 'settled'

export const THREAD_STATUS_META: Record<
  ThreadStatus,
  { label: string; cls: string; dotCls: string }
> = {
  active: {
    label: '近期活跃',
    cls: 'bg-emerald-50 text-emerald-700',
    dotCls: 'bg-emerald-500',
  },
  watching: {
    label: '观察中',
    cls: 'bg-amber-50 text-amber-700',
    dotCls: 'bg-amber-500',
  },
  settled: {
    label: '历史事件',
    cls: 'bg-gray-100 text-gray-500',
    dotCls: 'bg-gray-400',
  },
}

/** 活跃/观察的分界（小时） */
export const THREAD_ACTIVE_HOURS = 24
export const THREAD_WATCHING_HOURS = 72

export function deriveThreadStatus(lastSeenAt: string, now = Date.now()): ThreadStatus {
  const t = new Date(lastSeenAt).getTime()
  if (Number.isNaN(t)) return 'settled'
  const hours = (now - t) / 3_600_000
  if (hours < THREAD_ACTIVE_HOURS) return 'active'
  if (hours < THREAD_WATCHING_HOURS) return 'watching'
  return 'settled'
}
