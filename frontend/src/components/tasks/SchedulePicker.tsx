/**
 * SchedulePicker：面向非技术用户的采集频率控件。
 *
 * 用「每 30 分钟 / 每小时 / 每 6 小时 / 每天 / 每周 / 每月 / 自定义」+ 时间选择器
 * 取代裸 Cron 输入；内部始终以**本地时间**编辑、保存为 UTC Cron，并把最终写入的
 * 表达式明示在下方，用户可以核对、不留黑盒。
 */
import { WEEKDAY_OPTIONS, SCHEDULE_PRESETS, buildCron, parseSchedule, describeCron,
         localTimeZoneLabel, type ScheduleValue } from '../../utils/schedule'
import { clsx } from 'clsx'

interface SchedulePickerProps {
  /** 当前 Cron 表达式（UTC，后端求值口径） */
  value: string
  onChange: (cron: string) => void
}

const pad = (n: number) => String(n).padStart(2, '0')

export function SchedulePicker({ value, onChange }: SchedulePickerProps) {
  const schedule = parseSchedule(value)
  const tz = localTimeZoneLabel()
  const isCustom = schedule.mode === 'custom'

  const update = (patch: Partial<ScheduleValue>) => {
    onChange(buildCron({ ...schedule, ...patch }))
  }

  const customInvalid = isCustom && schedule.custom.trim().split(/\s+/).length !== 5

  return (
    <div className="space-y-3">
      {/* 频率预设 */}
      <div role="group" aria-label="采集频率" className="flex flex-wrap gap-2">
        {SCHEDULE_PRESETS.map((preset) => (
          <button
            key={preset.mode}
            type="button"
            aria-pressed={schedule.mode === preset.mode}
            onClick={() => update({ mode: preset.mode })}
            className={clsx(
              'px-3 py-1 rounded-full text-xs border transition-colors',
              schedule.mode === preset.mode
                ? 'bg-primary-600 text-white border-primary-600'
                : 'border-gray-300 text-gray-600 hover:border-primary-400'
            )}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* 具体时刻 / 星期 / 日期 */}
      {(schedule.mode === 'daily' || schedule.mode === 'weekly' || schedule.mode === 'monthly') && (
        <div className="flex flex-wrap items-end gap-3">
          {schedule.mode === 'weekly' && (
            <div>
              <label htmlFor="schedule-weekday" className="block text-xs text-gray-500 mb-1">
                星期
              </label>
              <select
                id="schedule-weekday"
                className="input"
                value={schedule.weekday}
                onChange={(e) => update({ weekday: Number(e.target.value) })}
              >
                {WEEKDAY_OPTIONS.map((w) => (
                  <option key={w.value} value={w.value}>{w.label}</option>
                ))}
              </select>
            </div>
          )}

          {schedule.mode === 'monthly' && (
            <div>
              <label htmlFor="schedule-day" className="block text-xs text-gray-500 mb-1">
                每月几号
              </label>
              <select
                id="schedule-day"
                className="input"
                value={schedule.day}
                onChange={(e) => update({ day: Number(e.target.value) })}
              >
                {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>{d} 日</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label htmlFor="schedule-time" className="block text-xs text-gray-500 mb-1">
              时间（{tz}）
            </label>
            <input
              id="schedule-time"
              type="time"
              className="input"
              value={`${pad(schedule.hour)}:${pad(schedule.minute)}`}
              onChange={(e) => {
                const [h, m] = e.target.value.split(':').map(Number)
                if (Number.isInteger(h) && Number.isInteger(m)) update({ hour: h, minute: m })
              }}
            />
          </div>
        </div>
      )}

      {/* 自定义：给进阶用户留的口子 */}
      {isCustom && (
        <div>
          <label htmlFor="schedule-custom" className="block text-xs text-gray-500 mb-1">
            Cron 表达式（5 段：分 时 日 月 周，UTC）
          </label>
          <input
            id="schedule-custom"
            className="input font-mono text-sm"
            placeholder="0 1 * * *"
            value={schedule.custom}
            onChange={(e) => update({ custom: e.target.value })}
            aria-invalid={customInvalid}
          />
          {customInvalid && (
            <p className="text-xs text-red-500 mt-1">Cron 需要 5 段，例如 0 1 * * *</p>
          )}
        </div>
      )}

      {/* 换算结果：让用户看得见最终保存的值 */}
      <p className="text-xs text-gray-500">
        下次运行：<span className="text-gray-700">{describeCron(value)}</span>
        <span className="mx-1.5 text-gray-300">·</span>
        保存为 Cron <code className="font-mono text-gray-700">{value || '—'}</code>
        <span className="text-gray-400">（服务器按 UTC 调度）</span>
      </p>
    </div>
  )
}
