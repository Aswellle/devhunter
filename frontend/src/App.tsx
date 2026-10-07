import { useEffect, useRef } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'

import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { defaultMutationOptions } from './hooks/useOptimisticMutation'
import { useAuthStore } from './stores/authStore'
import { AppLayout } from './components/layout/AppLayout'
import { LoginPage } from './pages/LoginPage'
import { ItemsPage } from './pages/ItemsPage'
import { TasksPage } from './pages/TasksPage'
import { StarredPage } from './pages/StarredPage'
import { DashboardPage } from './pages/DashboardPage'
import { CloudPage } from './pages/CloudPage'
import { ProfilePage } from './pages/ProfilePage'
import { RecommendPage } from './pages/RecommendPage'
import { MorePage } from './pages/MorePage'

function AuthExpiredHandler() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const location = useLocation()
  const handledRef = useRef(false)
  useEffect(() => {
    const handler = () => {
      // 多个并发请求同时 401 时只处理一次，避免重复登出/跳转
      if (handledRef.current) return
      handledRef.current = true
      logout()
      navigate('/login', { replace: true })
    }
    window.addEventListener('devhunter:auth-expired', handler)
    return () => window.removeEventListener('devhunter:auth-expired', handler)
  }, [navigate, logout])
  // 回到登录页后重置一次性守卫，用户重新登录后的再次过期仍能正常触发
  useEffect(() => {
    if (location.pathname === '/login') handledRef.current = false
  }, [location.pathname])
  return null
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
    // 接入全局 mutation 默认值：网络错误重试 1 次、4xx 不重试
    mutations: defaultMutationOptions.mutations,
  },
})

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthExpiredHandler />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/*"
            element={
              <AuthGuard>
                <AppLayout>
                  <ErrorBoundary>
                    <Routes>
                      <Route path="/"           element={<ItemsPage />} />
                      <Route path="/tasks"      element={<TasksPage />} />
                      <Route path="/cloud"      element={<CloudPage />} />
                      <Route path="/starred"    element={<StarredPage />} />
                      <Route path="/dashboard"  element={<DashboardPage />} />
                      <Route path="/recommend"  element={<RecommendPage />} />
                      <Route path="/profile" element={<ProfilePage />} />
                      <Route path="/more"    element={<MorePage />} />
                      <Route path="*"           element={<Navigate to="/" replace />} />
                    </Routes>
                  </ErrorBoundary>
                </AppLayout>
              </AuthGuard>
            }
          />
        </Routes>
      </BrowserRouter>
      <Toaster
        toastOptions={{
          duration: 3000,
          style: { fontSize: '14px' },
        }}
      />
    </QueryClientProvider>
  )
}
