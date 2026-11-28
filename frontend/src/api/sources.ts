/**
 * F1: sources API — 使用统一 axios client（而非裸 fetch），
 * 确保 401 拦截、Cookie 传递、错误格式一致。
 */
import client from './client'
import type { DiscoveryResult, PreviewResult, TestResult } from '../types'

// discover/test 端点需要更长的超时时间（外部抓取操作可能需数十秒至数分钟）
const LONG_TIMEOUT = 120_000

export interface OpmlPreviewEntry {
  title: string
  xml_url: string
  html_url: string
  /** SSRF 预检通过 */
  safe: boolean
  /** 不通过时的原因 */
  error: string
  /** 与既有来源地址重复 */
  duplicate: boolean
}

export const sourcesApi = {
  discover: (url: string) =>
    client.post<DiscoveryResult>('/sources/discover', { url }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  preview: (url: string, discoveryResult?: DiscoveryResult) =>
    client.post<PreviewResult>('/sources/preview', { url, discovery_result: discoveryResult }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  test: (url: string, selectors: Record<string, string>, expectedMinItems?: number) =>
    client.post<TestResult>('/sources/test', { url, selectors, expected_min_items: expectedMinItems }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  opmlPreview: (content: string) =>
    client.post<{
      entries: OpmlPreviewEntry[]
      total: number
      duplicates: number
      unsafe: number
    }>('/sources/opml/preview', { content }, { timeout: LONG_TIMEOUT }).then((r) => r.data),

  opmlImport: (entries: Array<{ xml_url: string; title: string; html_url: string }>) =>
    client.post<{
      created: number
      skipped_duplicate: number
      skipped_unsafe: number
      errors: string[]
    }>('/sources/opml/import', { entries }).then((r) => r.data),
}
