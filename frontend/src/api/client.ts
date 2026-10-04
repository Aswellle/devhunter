import axios from 'axios'
import type { AxiosError } from 'axios'

/**
 * 标准化错误格式 - 将 AxiosError 转换为统一的 ApiError
 */
export interface ApiError {
  status: number
  code: string
  message: string
  details?: unknown
}

function normalizeError(err: AxiosError): ApiError {
  const status = err.response?.status ?? 0
  const data = err.response?.data as Record<string, unknown> | undefined
  // 后端统一错误体是 {"error": {"code", "message", "details"}}，这里必须解包，
  // 否则前端只会显示 axios 的 "Request failed with status code 400"
  const envelope = (data?.error ?? undefined) as Record<string, unknown> | undefined

  return {
    status,
    code: (envelope?.code as string) || (data?.code as string) || err.code || 'UNKNOWN_ERROR',
    message: (envelope?.message as string) || (data?.message as string) || err.message || '请求失败',
    details: envelope?.details ?? data?.details,
  }
}

/**
 * 从任意 catch 值里取出可展示的错误文案。
 *
 * 拦截器把 AxiosError 归一化成 ApiError，所以调用方拿到的不是 axios 错误，
 * 不能再读 e.response.data.error.message。
 */
export function errorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null && 'message' in err) {
    const { message } = err
    if (typeof message === 'string' && message) return message
  }
  return fallback
}

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // 启用跨域 Cookie（发送 httpOnly Cookie）
  withCredentials: true,
})

// GET 请求的自动重试配置（网络错误 / 5xx / 超时）
const MAX_RETRIES = 2
const RETRY_DELAY = 1000

// 响应拦截器：
// 1. GET 的网络错误/5xx/超时自动重试（幂等安全；POST 等写操作绝不重试，避免重复副作用）
// 2. 业务 401 派发认证失效事件（登录/登出自身的 401 除外，否则会造成请求风暴）
client.interceptors.response.use(
  (res) => res,
  async (err) => {
    const config = err.config as (typeof err.config & { __retryCount?: number }) | undefined
    const status: number = err.response?.status ?? 0
    const method = (config?.method ?? '').toLowerCase()
    const canceled = err.code === 'ERR_CANCELED'
    const retriable = !err.response || status >= 500 || err.code === 'ECONNABORTED'

    if (method === 'get' && !canceled && retriable && config && (config.__retryCount ?? 0) < MAX_RETRIES) {
      config.__retryCount = (config.__retryCount ?? 0) + 1
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY * config.__retryCount!))
      return client(config)
    }

    if (status === 401) {
      const url: string = config?.url ?? ''
      // /auth/login 失败（密码错误）与 /auth/logout 自身的 401 不代表会话过期；
      // 若照常派发事件会形成 logout() → POST /auth/logout → 401 → 再派发的无限循环
      const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/logout')
      if (!isAuthEndpoint) {
        // 清理 localStorage 认证标志
        localStorage.removeItem('devhunter_auth')
        // 派发自定义事件，由 App.tsx 处理登出和导航
        window.dispatchEvent(new CustomEvent('devhunter:auth-expired'))
      }
    }

    // 返回标准化错误
    return Promise.reject(normalizeError(err))
  }
)

export { normalizeError }
export default client
