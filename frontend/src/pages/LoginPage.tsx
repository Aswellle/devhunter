import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { Spinner } from '../components/ui/Spinner'
import { toast } from 'react-hot-toast'

export function LoginPage() {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(password)
      navigate('/')
    } catch {
      toast.error('密码错误，请重试')
      setPassword('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 flex items-stretch">
      {/* Left brand panel */}
      <div className="hidden md:flex flex-col justify-between w-80 bg-gray-800 border-r border-gray-700 p-10">
        {/* Logo & tagline */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <svg className="h-8 w-8 text-primary-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <path d="m21 21-4.35-4.35"/>
            </svg>
            <span className="text-white font-bold text-xl">DevHunter</span>
          </div>
          <p className="text-gray-400 text-sm leading-relaxed">
            全网开发需求与创意自动采集系统<br/>
            定时抓取 Hacker News、V2EX、GitHub 等平台
          </p>
        </div>

        {/* Feature highlights */}
        <div className="space-y-4">
          {[
            { label: '多平台采集', desc: '支持 5 大预设数据源模板' },
            { label: '智能去重', desc: '基于 URL Hash 的高效去重' },
            { label: '个性化推荐', desc: '基于阅读偏好智能推荐' },
          ].map((f) => (
            <div key={f.label} className="flex items-start gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-primary-400 mt-1.5 shrink-0" />
              <div>
                <div className="text-gray-200 text-sm font-medium">{f.label}</div>
                <div className="text-gray-500 text-xs mt-0.5">{f.desc}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <p className="text-gray-600 text-xs">
          密码通过 <code className="font-mono text-gray-500">AUTH_PASSWORD</code> 环境变量配置
        </p>
      </div>

      {/* Right login panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="md:hidden flex items-center gap-2 mb-8">
            <svg className="h-7 w-7 text-primary-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <path d="m21 21-4.35-4.35"/>
            </svg>
            <span className="text-white font-bold text-lg">DevHunter</span>
          </div>

          <h2 className="text-white text-xl font-bold mb-1">欢迎回来</h2>
          <p className="text-gray-400 text-sm mb-8">请输入访问密码进入系统</p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-gray-300 text-sm font-medium mb-2">访问密码</label>
              <input
                type="password"
                className="w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-4 py-3 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                placeholder="请输入访问密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
                required
              />
            </div>
            <button
              type="submit"
              className="w-full bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={loading || !password}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Spinner className="h-4 w-4" />验证中...
                </span>
              ) : '进入系统'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
