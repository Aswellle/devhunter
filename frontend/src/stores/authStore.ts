import { create } from 'zustand'

// 前端仅使用 localStorage 记录"已登录"标记（避免 XSS 通过 localStorage 读取真实 Token）
// 真正的 JWT 存储在后端设置的 httpOnly Cookie 中
const _AUTH_FLAG = 'devhunter_auth'

interface AuthState {
  isAuthenticated: boolean
  login: (password: string) => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: localStorage.getItem(_AUTH_FLAG) === '1',

  login: async (password: string) => {
    const { authApi } = await import('../api/auth')
    await authApi.login(password)
    // 后端已写入 httpOnly Cookie，前端只需记录标记
    localStorage.setItem(_AUTH_FLAG, '1')
    set({ isAuthenticated: true })
  },

  logout: () => {
    localStorage.removeItem(_AUTH_FLAG)
    set({ isAuthenticated: false })
    // best-effort：让服务端清除 httpOnly cookie。未认证时该请求返回 401 属预期，静默忽略
    import('../api/auth')
      .then(({ authApi }) => authApi.logout())
      .catch(() => {})
  },
}))
