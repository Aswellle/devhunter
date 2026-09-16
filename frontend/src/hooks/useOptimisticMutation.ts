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

/**
 * F3: 全局默认 mutation 配置 — 所有 mutation 默认启用乐观更新回滚模式。
 * 在 QueryClient 初始化时通过 `defaultOptions.mutations` 注入。
 */
export const defaultMutationOptions: DefaultOptions<Error> = {
  mutations: {
    // 网络错误时自动重试 1 次（不含 4xx 客户端错误）
    retry: (_failureCount: number, error: Error) => {
      // 不重试 4xx 错误（客户端问题，重试无意义）
      if ('status' in error && typeof error.status === 'number' && error.status >= 400 && error.status < 500) {
        return false
      }
      return _failureCount < 1
    },
    retryDelay: 1000,
  },
}
