export function formatDistanceToNow(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH} 小时前`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 30) return `${diffD} 天前`
  return date.toLocaleDateString('zh-CN')
}

export function formatDateTime(isoString: string): string {
  return new Date(isoString).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * 事件日志时钟：本地时区的 HH:MM:SS.mmm。
 *
 * 事件时间戳是后端写入的 UTC ISO 串，直接 slice 出来显示会让日志时间与
 * 用户本地时钟相差整个时区（如本地 12:58 显示 04:58），无法与"刚刚执行"
 * 的直觉对齐。这里统一转成本地时间；毫秒保留以呈现真实事件先后。
 */
export function formatLogClock(isoString: string): string {
  const d = new Date(isoString)
  if (Number.isNaN(d.getTime())) return isoString.slice(11, 23)
  const pad = (n: number, len = 2) => String(n).padStart(len, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}

/** 事件日志完整本地时间（悬停提示）：YYYY-MM-DD HH:MM:SS.mmm */
export function formatLogTimestamp(isoString: string): string {
  const d = new Date(isoString)
  if (Number.isNaN(d.getTime())) return isoString
  const pad = (n: number, len = 2) => String(n).padStart(len, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`
}
