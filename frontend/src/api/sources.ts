/**
 * sources API client
 */
import type { DiscoveryResult, PreviewResult, TestResult } from '../types'

const BASE = '/api/sources'

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.message || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const sourcesApi = {
  discover: (url: string) =>
    post<DiscoveryResult>('/discover', { url }),

  preview: (url: string, discoveryResult?: DiscoveryResult) =>
    post<PreviewResult>('/preview', { url, discovery_result: discoveryResult }),

  test: (url: string, selectors: Record<string, string>, expectedMinItems?: number) =>
    post<TestResult>('/test', { url, selectors, expected_min_items: expectedMinItems }),
}
