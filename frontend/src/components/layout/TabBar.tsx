/**
 * TabBar.tsx
 * 移动端底部导航栏（借鉴 AIHOT 的移动壳层 TabBar）。
 *
 * - 仅 md 以下显示（与桌面侧边栏的 md:flex 互补，二者互斥）
 * - 5 个主目的地；次要目的地（数据概览/结果云/我的画像/退出）收纳在 /more
 * - 安全区适配：pb 跟随 iOS 底部安全区
 */
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, MoreHorizontal, Rss, Sparkles, Star } from 'lucide-react'
import { clsx } from 'clsx'

const tabs = [
  { to: '/', label: '采集结果', icon: LayoutDashboard },
  { to: '/tasks', label: '任务管理', icon: Rss },
  { to: '/recommend', label: '今日推荐', icon: Sparkles },
  { to: '/starred', label: '已收藏', icon: Star },
  { to: '/more', label: '更多', icon: MoreHorizontal },
]

export function TabBar() {
  return (
    <nav
      aria-label="底部导航"
      className="fixed bottom-0 inset-x-0 z-30 md:hidden bg-gray-900 border-t border-gray-700 pb-[env(safe-area-inset-bottom)]"
    >
      <div className="grid grid-cols-5">
        {tabs.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px]',
                'text-[11px] font-medium transition-colors',
                'focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-400 outline-none',
                isActive ? 'text-primary-400' : 'text-gray-400 hover:text-gray-200',
              )
            }
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
