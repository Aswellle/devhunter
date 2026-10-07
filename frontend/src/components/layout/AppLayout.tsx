/**
 * AppLayout.tsx
 * 布局壳层：
 * - 桌面端（≥md）：左侧深色固定侧边栏 + 主内容区
 * - 移动端（<md）：顶部品牌栏 + 底部 TabBar（TabBar.tsx），
 *   次要目的地收纳在 /more 页。原来的汉堡抽屉已被 TabBar 取代并移除，
 *   减少一层覆盖交互；所有目的地在移动端仍两次点击内可达。
 */
import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { BarChart2, Cloud, LayoutDashboard, LogOut, Rss, Sparkles, Star, User } from 'lucide-react'
import { clsx } from 'clsx'
import { useAuthStore } from '../../stores/authStore'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { TabBar } from './TabBar'

const navItems = [
  { to: '/',          label: '采集结果', icon: LayoutDashboard },
  { to: '/tasks',     label: '任务管理', icon: Rss },
  { to: '/cloud',     label: '结果云',   icon: Cloud },
  { to: '/starred',   label: '已收藏',   icon: Star },
  { to: '/recommend', label: '今日推荐', icon: Sparkles },
  { to: '/dashboard', label: '数据概览', icon: BarChart2 },
  { to: '/profile',   label: '我的画像', icon: User },
]

function BrandMark() {
  return (
    <svg className="h-5 w-5 text-primary-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <title>DevHunter Logo</title>
      <circle cx="11" cy="11" r="8"/>
      <path d="m21 21-4.35-4.35"/>
    </svg>
  )
}

/** 桌面端侧边栏内容：Logo、主导航、退出登录（独立组件——仅此布局使用）。 */
function SidebarContent() {
  const { logout } = useAuthStore()
  const navigate   = useNavigate()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  return (
    <>
      {/* Logo */}
      <div className="px-5 py-4 border-b border-gray-700 shrink-0">
        <Link to="/" className="flex items-center gap-2">
          <BrandMark />
          <div>
            <span className="text-white font-bold text-base block leading-tight">
              DevHunter
            </span>
          </div>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="主导航">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-inset outline-none',
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white',
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 py-4 border-t border-gray-700 shrink-0">
        <button
          onClick={() => setShowLogoutConfirm(true)}
          className="flex w-full items-center gap-2.5 px-3 py-2 rounded-md
                     text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
        >
          <LogOut className="h-4 w-4" />
          退出登录
        </button>
      </div>

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
    </>
  )
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* 键盘用户跳过导航直达主内容（获得焦点时才可见） */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:z-[300] focus:top-2 focus:left-2
                   focus:bg-primary-600 focus:text-white focus:px-3 focus:py-2 focus:rounded-md focus:text-sm"
      >
        跳到主内容
      </a>

      {/*
       * ── 桌面端侧边栏 ──────────────────────────────────
       * hidden md:flex → 移动端隐藏，桌面端显示为 flex
       * 无 position/z-index/transform → 不创建任何层叠上下文
       * 作为普通 flex item 参与布局，主内容 flex-1 自动占据剩余宽度
       */}
      <aside className="hidden md:flex md:flex-col md:w-56 md:shrink-0 bg-gray-900">
        <SidebarContent />
      </aside>

      {/* ── 主内容区 ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* 移动端品牌顶栏 */}
        <header className="md:hidden flex items-center gap-2 px-4 py-3
                            bg-gray-900 border-b border-gray-700 shrink-0 z-10">
          <Link to="/" className="flex items-center gap-2" aria-label="DevHunter 首页">
            <BrandMark />
            <span className="text-white font-bold text-sm">DevHunter</span>
          </Link>
        </header>

        {/* pb 为移动端底部 TabBar 留出空间（含 iOS 安全区） */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto bg-gray-50 pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0">
          {children}
        </main>
      </div>

      <TabBar />
    </div>
  )
}
