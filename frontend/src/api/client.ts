import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // 启用跨域 Cookie（发送 httpOnly Cookie）
  withCredentials: true,
})

// 响应拦截器：401 时派发认证失效事件，由 App 层以 React Router 方式处理
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      // Clear the localStorage auth flag set by authStore; the JWT itself lives in
      // an httpOnly cookie and is never accessible to JS, so it's not touched here.
      localStorage.removeItem('devhunter_auth')
      // Dispatch a custom event; App.tsx's AuthExpiredHandler logs out + navigates.
      window.dispatchEvent(new CustomEvent('devhunter:auth-expired'))
    }
    return Promise.reject(err)
  }
)

export default client
