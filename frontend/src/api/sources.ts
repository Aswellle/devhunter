/**
 * F1: sources API — 使用统一 axios client（而非裸 fetch），
 * 确保 401 拦截、Cookie 传递、错误格式一致。
 */
import client from './client'
import type { DiscoveryResult, PreviewResult, TestResult } from '../types'

export const sourcesApi = {
  discover: (url: string) =>
    client.post<DiscoveryResult>('/sources/discover', { url }).then((r) => r.data),

  preview: (url: string, discoveryResult?: DiscoveryResult) =>
    client.post<PreviewResult>('/sources/preview', { url, discovery_result: discoveryResult }).then((r) => r.data),

  test: (url: string, selectors: Record<string, string>, expectedMinItems?: number) =>
    client.post<TestResult>('/sources/test', { url, selectors, expected_min_items: expectedMinItems }).then((r) => r.data),
}
