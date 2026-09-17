/**
 * F1: sources API — 使用统一 axios client（而非裸 fetch），
 * 确保 401 拦截、Cookie 传递、错误格式一致。
 */
import client from './client'
import type { DiscoveryResult, PreviewResult, TestResult } from '../types'

// discover/test 端点需要更长的超时时间（外部抓取操作可能需数十秒至数分钟）
const LONG_TIMEOUT = 120_000

export const sourcesApi = {
  discover: (url: string) =>
    client.post<DiscoveryResult>('/sources/discover', { url }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  preview: (url: string, discoveryResult?: DiscoveryResult) =>
    client.post<PreviewResult>('/sources/preview', { url, discovery_result: discoveryResult }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  test: (url: string, selectors: Record<string, string>, expectedMinItems?: number) =>
    client.post<TestResult>('/sources/test', { url, selectors, expected_min_items: expectedMinItems }, { timeout: LONG_TIMEOUT }).then((r) => r.data),
}
