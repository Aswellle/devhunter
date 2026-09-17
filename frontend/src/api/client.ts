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

  return {
    status,
    code: (data?.code as string) || err.code || 'UNKNOWN_ERROR',
    message: (data?.message as string) || err.message || '请求失败',
    details: data?.details,
  }
}

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // 启用跨域 Cookie（发送 httpOnly Cookie）
  withCredentials: true,
})

// 请求重试配置
const MAX_RETRIES = 2
const RETRY_DELAY = 1000

async function retryRequest<T>(fn: () => Promise<T>, retries = MAX_RETRIES): Promise<T> {
  try {
    return await fn()
  } catch (err) {
    const axiosErr = err as AxiosError
    // 只重试网络错误或 5xx 服务器错误，不重试 4xx 客户端错误
    const shouldRetry =
      !axiosErr.response || // 网络错误
      axiosErr.response.status >= 500 || // 服务器错误
      axiosErr.code === 'ECONNABORTED' // 超时

    if (retries > 0 && shouldRetry) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY * (MAX_RETRIES - retries + 1)))
      return retryRequest(fn, retries - 1)
    }
    throw err
  }
}

// 响应拦截器：401 时清理缓存并派发认证失效事件
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // 清理 localStorage 认证标志
      localStorage.removeItem('devhunter_auth')
      // 派发自定义事件，由 App.tsx 处理登出和导航
      window.dispatchEvent(new CustomEvent('devhunter:auth-expired'))
    }
    // 返回标准化错误
    return Promise.reject(normalizeError(err))
  }
)

export { retryRequest, normalizeError }
export default client
