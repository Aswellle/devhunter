/**
 * AppLayout.tsx
 * 修复：
 * 1. 移除桌面端侧边栏的 CSS transform（md:translate-x-0），消除零值 transform
 *    导致的意外层叠上下文。
 * 2. 桌面端侧边栏改用纯 static/relative 定位，不需要任何 z-index。
 * 3. 移动端使用独立的 fixed 覆盖层，与桌面端结构完全分离，互不干扰。
 */
import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { BarChart2, Cloud, LayoutDashboard, LogOut, Menu, Rss, Sparkles, Star, X } from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { clsx } from 'clsx'

const navItems = [
  { to: '/',          label: '采集结果', icon: LayoutDashboard },
  { to: '/tasks',     label: '任务管理', icon: Rss },
  { to: '/cloud',     label: '结果云',   icon: Cloud },
  { to: '/starred',   label: '已收藏',   icon: Star },
  { to: '/recommend', label: '今日推荐', icon: Sparkles },
  { to: '/dashboard', label: '数据概览', icon: BarChart2 },
]

interface SidebarContentProps {
  onLinkClick?: () => void
}

function SidebarContent({ onLinkClick }: SidebarContentProps) {
  const { logout } = useAuthStore()
  const navigate   = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <>
      {/* Logo */}
      <div className="px-5 py-4 border-b border-gray-700 shrink-0">
        <Link to="/" className="flex items-center gap-2" onClick={onLinkClick}>
          {/* SVG 搜索图标替代 emoji */}
          <svg className="h-5 w-5 text-primary-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <div>
            <span className="text-white font-bold text-base block leading-tight">
              DevHunter
            </span>
            <span className="text-gray-400 text-xs">全网需求采集</span>
          </div>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={onLinkClick}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors',
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
          onClick={handleLogout}
          className="flex w-full items-center gap-2.5 px-3 py-2 rounded-md
                     text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
        >
          <LogOut className="h-4 w-4" />
          退出登录
        </button>
      </div>
    </>
  )
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden">

      {/*
       * ── 桌面端侧边栏 ──────────────────────────────────
       * hidden md:flex  → 移动端隐藏，桌面端显示为 flex
       * 无 position/z-index/transform → 不创建任何层叠上下文
       * 作为普通 flex item 参与布局，主内容 flex-1 自动占据剩余宽度
       */}
      <aside className="hidden md:flex md:flex-col md:w-56 md:shrink-0 bg-gray-900">
        <SidebarContent />
      </aside>

      {/*
       * ── 移动端侧边栏（抽屉式覆盖层）──────────────────
       * 与桌面端完全独立，只在 mobile 下渲染。
       * fixed inset-0 z-40 确保覆盖全屏（低于模态框 z-50/z-200）。
       */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          {/* 侧边栏内容 */}
          <div className="w-64 flex flex-col bg-gray-900 shrink-0 shadow-2xl">
            {/* 关闭按钮 */}
            <div className="flex justify-end px-3 pt-3">
              <button
                className="text-gray-400 hover:text-white p-1 rounded"
                onClick={() => setSidebarOpen(false)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarContent onLinkClick={() => setSidebarOpen(false)} />
          </div>
          {/* 遮罩：点击关闭 */}
          <div
            className="flex-1 bg-black/60"
            onClick={() => setSidebarOpen(false)}
          />
        </div>
      )}

      {/* ── 主内容区 ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* 移动端顶栏（z-10 确保位于面板下方，面板有自己的关闭按钮） */}
        <header className="md:hidden flex items-center gap-3 px-4 py-3
                            bg-gray-900 border-b border-gray-700 shrink-0 z-10">
          <button
            className="text-gray-300 hover:text-white p-1"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-white font-bold text-sm">DevHunter</span>
        </header>

        <main className="flex-1 overflow-y-auto bg-gray-50">
          {children}
        </main>
      </div>
    </div>
  )
}
