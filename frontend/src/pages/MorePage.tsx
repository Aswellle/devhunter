/**
 * MorePage.tsx
 * 「更多」页：移动端底部 TabBar 的第 5 个目的地，收纳次要导航与退出登录。
 * 桌面端这些入口常驻侧边栏，此页仅作为移动壳层的补充（桌面访问亦无害）。
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BarChart2, ChevronRight, Cloud, LogOut, User } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'

const moreLinks = [
  { to: '/dashboard', label: '数据概览', desc: '采集系统运行状态与统计', icon: BarChart2 },
  { to: '/cloud', label: '结果云', desc: '关键词聚合视图', icon: Cloud },
  { to: '/profile', label: '我的画像', desc: '兴趣主题与阅读偏好、RSS 订阅', icon: User },
]

export function MorePage() {
  const { logout } = useAuthStore()
  const navigate = useNavigate()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
      <h1 className="text-xl font-bold text-gray-900">更多</h1>
      <p className="text-sm text-gray-500 mt-0.5 mb-6">系统功能与账户</p>

      <div className="card divide-y divide-gray-100 overflow-hidden">
        {moreLinks.map(({ to, label, desc, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="flex items-center gap-3 px-4 py-3.5 hover:bg-gray-50 transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-400 outline-none"
          >
            <span className="h-9 w-9 rounded-lg bg-primary-50 flex items-center justify-center shrink-0">
              <Icon className="h-5 w-5 text-primary-600" aria-hidden="true" />
            </span>
            <span className="flex-1 min-w-0">
              <span className="block text-sm font-medium text-gray-900">{label}</span>
              <span className="block text-xs text-gray-400 mt-0.5">{desc}</span>
            </span>
            <ChevronRight className="h-4 w-4 text-gray-300 shrink-0" aria-hidden="true" />
          </Link>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setShowLogoutConfirm(true)}
        className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg
                   text-sm font-medium text-danger bg-danger-light hover:bg-red-100 transition-colors
                   focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-danger outline-none"
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        退出登录
      </button>

      {showLogoutConfirm && (
        <ConfirmDialog
          title="退出登录"
          message="确定要退出登录吗？"
          confirmText="退出"
          cancelText="取消"
          variant="danger"
          onConfirm={() => {
            logout()
            navigate('/login')
          }}
          onCancel={() => setShowLogoutConfirm(false)}
        />
      )}
    </div>
  )
}
