/**
 * ErrorBoundary：全局错误边界
 *
 * 捕获子组件树的渲染异常，防止整个应用白屏。
 * 展示友好降级 UI 并提供重试机制。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Caught render error:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center" role="alert">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-lg font-semibold text-primary mb-2">页面出现异常</h2>
          <p className="text-sm text-secondary mb-4 max-w-md">
            渲染过程中发生了错误。请尝试刷新页面或联系管理员。
          </p>
          {this.state.error && (
            <pre className="text-xs text-muted bg-hover rounded p-3 mb-4 max-w-full overflow-auto text-left">
              {this.state.error.message}
            </pre>
          )}
          <div className="flex gap-3">
            <button onClick={this.handleReset} className="btn-primary">
              重试
            </button>
            <button onClick={() => window.location.reload()} className="btn-ghost">
              刷新页面
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
