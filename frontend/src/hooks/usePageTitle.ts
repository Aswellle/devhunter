import { useEffect } from 'react'

/**
 * 页面级 document.title：多标签页与浏览器历史中可辨识当前视图。
 * 未传 title 时回落到应用名（如登出后的登录页过渡）。
 */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · DevHunter` : 'DevHunter'
  }, [title])
}
