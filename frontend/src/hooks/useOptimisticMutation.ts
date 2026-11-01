/**
 * F3: 乐观更新 + 回滚的通用 mutation hook。
 *
 * 用法：
 *   const mutation = useOptimisticMutation({
 *     mutationFn: (vars) => api.batchPatch(ids, data),
 *     onMutate: async (vars) => {
 *       const previous = qc.getQueryData(queryKey)
 *       qc.setQueryData(queryKey, (old) => optimisticUpdate(old, vars))
 *       return { previous }  // 返回 context 用于回滚
 *     },
 *     onError: (_err, _vars, context) => {
 *       // 回滚到变更前的状态
 *       if (context?.previous) qc.setQueryData(queryKey, context.previous)
 *     },
 *     onSettled: () => {
 *       // 最终与服务端同步
 *       qc.invalidateQueries({ queryKey })
 *     },
 *   })
 */
import type { DefaultOptions } from '@tanstack/react-query'
import type { ApiError } from '../api/client'

/**
 * 类型谓词：检查错误是否为 ApiError
 */
function isApiError(error: Error | ApiError): error is ApiError {
  return 'status' in error && typeof error.status === 'number' && 'code' in error
}

/**
 * F3: 全局默认 mutation 配置 — 所有 mutation 默认启用乐观更新回滚模式。
 * 在 QueryClient 初始化时通过 `defaultOptions.mutations` 注入。
 */
export const defaultMutationOptions: DefaultOptions<Error> = {
  mutations: {
    // 仅对幂等请求重试 1 次。POST 等非幂等写操作绝不重试：请求可能已到达
    // 服务端（超时/连接重置时响应丢失），重试会产生重复任务/重复副作用——
    // 与 axios 拦截器"POST 不重试"是同一条纪律，不能在 TanStack 层绕过。
    retry: (_failureCount: number, error: Error | ApiError) => {
      if (!isApiError(error)) return false
      // 4xx 是客户端问题，重试无意义
      if (error.status >= 400 && error.status < 500) {
        return false
      }
      const method = error.method ?? ''
      const idempotent = ['get', 'head', 'put', 'patch', 'delete'].includes(method)
      return idempotent && _failureCount < 1
    },
    // 指数退避：1s → 2s → 4s
    retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 10000),
  },
}
