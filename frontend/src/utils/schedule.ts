/**
 * 采集频率：本地时间 ↔ UTC Cron 的互转与人类可读描述。
 *
 * 后端用 APScheduler 的 CronTrigger 在 **UTC** 下求值
 * （scheduler/manager.py 中 timezone=datetime.timezone.utc），
 * 而用户想的是「每天 9 点」这样的本地时间，所以这里统一以本地时间编辑、
 * 保存前换算成 UTC，并把换算结果明明白白展示出来。
 *
 * day_of_week 采用 APScheduler 约定：0=周一 … 6=周日（不是 crontab 的 0=周日）。
 * 识别不了的表达式一律回落到「自定义」并原样保留，绝不静默改写用户配置。
 */

export type ScheduleMode =
  | 'every_30min'
  | 'every_hour'
  | 'every_6h'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'custom'

export interface ScheduleValue {
  mode: ScheduleMode
  hour: number
  minute: number
  /** 0=周一 … 6=周日（APScheduler 约定） */
  weekday: number
  /** 本地日号 1-31 */
  day: number
  custom: string
}

export const WEEKDAY_OPTIONS = [
  { value: 0, label: '周一' },
  { value: 1, label: '周二' },
  { value: 2, label: '周三' },
  { value: 3, label: '周四' },
  { value: 4, label: '周五' },
  { value: 5, label: '周六' },
  { value: 6, label: '周日' },
] as const

export const SCHEDULE_PRESETS: ReadonlyArray<{ mode: ScheduleMode; label: string }> = [
  { mode: 'every_30min', label: '每 30 分钟' },
  { mode: 'every_hour', label: '每小时' },
  { mode: 'every_6h', label: '每 6 小时' },
  { mode: 'daily', label: '每天' },
  { mode: 'weekly', label: '每周' },
  { mode: 'monthly', label: '每月' },
  { mode: 'custom', label: '自定义' },
]

/** 不需要额外参数的固定频率 */
const FIXED_CRONS: ReadonlyArray<{ cron: string; mode: ScheduleMode }> = [
  { cron: '*/30 * * * *', mode: 'every_30min' },
  { cron: '0 * * * *', mode: 'every_hour' },
  { cron: '0 */6 * * *', mode: 'every_6h' },
]

const pad = (n: number) => String(n).padStart(2, '0')

/** 本地时区标签，如 UTC+8 */
export function localTimeZoneLabel(): string {
  const offsetMinutes = -new Date().getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  const hours = Math.floor(abs / 60)
  const minutes = abs % 60
  return `UTC${sign}${hours}${minutes ? `:${pad(minutes)}` : ''}`
}

export function defaultSchedule(): ScheduleValue {
  const base: ScheduleValue = {
    mode: 'daily', hour: 9, minute: 0, weekday: 0, day: 1, custom: '',
  }
  return { ...base, custom: buildCron(base) }
}

/** 取一个「本地时间 = 目标时间，且本地星期/日号匹配」的参考日期 */
function localReference(v: ScheduleValue): Date {
  const now = new Date()
  if (v.mode === 'weekly') {
    // APS 0=周一 → JS 1=周一；APS 6=周日 → JS 0
    const targetJsDay = (v.weekday + 1) % 7
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate(), v.hour, v.minute, 0, 0)
    d.setDate(d.getDate() + ((targetJsDay - d.getDay() + 7) % 7))
    return d
  }
  if (v.mode === 'monthly') {
    // 用 28 号以内的等效日期取时区偏移，避免 31 号在小月回退到次月
    return new Date(now.getFullYear(), now.getMonth(), Math.min(v.day, 28), v.hour, v.minute, 0, 0)
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), v.hour, v.minute, 0, 0)
}

/** 本地时间 → UTC Cron */
export function buildCron(v: ScheduleValue): string {
  if (v.mode === 'custom') return (v.custom || '').trim()

  const fixed = FIXED_CRONS.find((f) => f.mode === v.mode)
  if (fixed) return fixed.cron

  const ref = localReference(v)
  const minute = ref.getUTCMinutes()
  const hour = ref.getUTCHours()

  if (v.mode === 'weekly') return `${minute} ${hour} * * ${(ref.getUTCDay() + 6) % 7}`
  if (v.mode === 'monthly') return `${minute} ${hour} ${ref.getUTCDate()} * *`
  return `${minute} ${hour} * * *`
}

/**
 * 是否为调度器可接受的 Cron（与 SchedulePicker 的 customInvalid 同口径：5 段）。
 * 只做段数校验、不深入字段语法——APScheduler 接受的字段写法很多（步进、列表、区间皆可），
 * 过度校验会误拦合法表达式；字段级错误交给后端 422 并由 errorMessage 透出。
 */
export function isValidCronExpression(cron: string): boolean {
  const raw = (cron || '').trim()
  if (!raw) return false
  return raw.split(/\s+/).length === 5
}

/** UTC Cron → 本地可编辑值（识别不了的返回 mode='custom'） */
export function parseSchedule(cron: string): ScheduleValue {
  const base = defaultSchedule()
  const raw = (cron || '').trim()

  const fixed = FIXED_CRONS.find((f) => f.cron === raw)
  if (fixed) return { ...base, mode: fixed.mode, custom: raw }

  const parts = raw.split(/\s+/)
  if (parts.length !== 5) return { ...base, mode: 'custom', custom: raw || base.custom }

  const [mi, h, dom, mon, dow] = parts
  if (mon !== '*' || !/^\d+$/.test(mi) || !/^\d+$/.test(h)) {
    return { ...base, mode: 'custom', custom: raw }
  }
  if (dow !== '*' && !/^[0-6]$/.test(dow)) return { ...base, mode: 'custom', custom: raw }
  if (dom !== '*' && (!/^\d+$/.test(dom) || Number(dom) < 1 || Number(dom) > 31)) {
    return { ...base, mode: 'custom', custom: raw }
  }

  const now = new Date()
  const utcTime = { hour: Number(h), minute: Number(mi) }

  if (dow !== '*') {
    let ref = new Date(Date.UTC(
      now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), utcTime.hour, utcTime.minute,
    ))
    while ((ref.getUTCDay() + 6) % 7 !== Number(dow)) {
      ref = new Date(ref.getTime() + 86_400_000)
    }
    return {
      ...base, mode: 'weekly', custom: raw,
      hour: ref.getHours(), minute: ref.getMinutes(), weekday: (ref.getDay() + 6) % 7,
    }
  }

  if (dom !== '*') {
    const ref = new Date(Date.UTC(
      now.getUTCFullYear(), now.getUTCMonth(), Number(dom), utcTime.hour, utcTime.minute,
    ))
    return {
      ...base, mode: 'monthly', custom: raw,
      hour: ref.getHours(), minute: ref.getMinutes(), day: ref.getDate(),
    }
  }

  const ref = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), utcTime.hour, utcTime.minute,
  ))
  return { ...base, mode: 'daily', custom: raw, hour: ref.getHours(), minute: ref.getMinutes() }
}

/**
 * Cron → 中文描述（按本地时间表述，便于非技术用户核对）。
 *
 * 时区偏移按当前日期计算，跨夏令时切换的边界会有小时级误差，
 * 因此界面上始终同时展示真实保存的 Cron 表达式。
 */
export function describeCron(cron: string): string {
  const raw = (cron || '').trim()
  if (!raw) return '未设置'

  const fixed = FIXED_CRONS.find((f) => f.cron === raw)
  if (fixed) return SCHEDULE_PRESETS.find((p) => p.mode === fixed.mode)?.label ?? raw

  const parts = raw.split(/\s+/)
  if (parts.length !== 5 || parts[3] !== '*') return `自定义（${raw}）`

  const [mi, h, dom, dow] = parts
  const everyMin = /^\*\/(\d+)$/.exec(mi)
  if (everyMin && h === '*' && dom === '*' && dow === '*') return `每 ${everyMin[1]} 分钟`
  const everyHour = /^\*\/(\d+)$/.exec(h)
  if (mi === '0' && everyHour && dom === '*' && dow === '*') return `每 ${everyHour[1]} 小时`
  if (/^\d+$/.test(mi) && h === '*' && dom === '*' && dow === '*') {
    return `每小时的第 ${Number(mi)} 分钟`
  }

  const schedule = parseSchedule(raw)
  const time = `${pad(schedule.hour)}:${pad(schedule.minute)}`
  if (schedule.mode === 'daily') return `每天 ${time}`
  if (schedule.mode === 'weekly') {
    const label = WEEKDAY_OPTIONS.find((w) => w.value === schedule.weekday)?.label ?? `周${schedule.weekday}`
    return `每${label} ${time}`
  }
  if (schedule.mode === 'monthly') return `每月 ${schedule.day} 日 ${time}`

  return `自定义（${raw}）`
}
