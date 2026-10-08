/**
 * F2: Query Key 规范化 — 统一的 query key 工厂。
 *
 * 所有 TanStack Query 的 key 必须通过此工厂生成，禁止直接使用字面量 key。
 * 确保：
 * - invalidate 时能精确匹配
 * - 命名风格一致
 * - 避免 key 散落在各处导致遗漏 invalidate
 *
 * @example
 * // ✅ 正确：使用工厂函数
 * queryKey: queryKeys.items.grouped(filters)
 * // ❌ 错误：使用字面量 key
 * queryKey: ['items', 'grouped', filters]
 */
export const queryKeys = {
  // ── Items ──────────────────────────────────────────────
  items: {

    all: ['items'] as const,
    grouped: (filters: Record<string, unknown> | undefined) =>
      ['items', 'grouped', filters] as const,
    counts: () => ['items', 'counts'] as const,
    detail: (id: string) => ['items', 'detail', id] as const,
    // 收藏列表按页缓存；starredAll 用于跨页失效（前缀匹配）
    starred: (page: number = 1) => ['items', 'starred', page] as const,
    starredAll: ['items', 'starred'] as const,
    cloud: () => ['items', 'cloud'] as const,
  },

  // ── Tasks ──────────────────────────────────────────────
  tasks: {
    all: ['tasks'] as const,
    list: (params: Record<string, unknown> | undefined) =>
      ['tasks', 'list', params] as const,
    detail: (id: string) => ['tasks', 'detail', id] as const,
    executions: (id: string, params: Record<string, unknown> | undefined) =>
      ['tasks', 'executions', id, params] as const,
    templates: () => ['tasks', 'templates'] as const,
  },

  // ── Threads ────────────────────────────────────────────
  threads: {
    all: ['threads'] as const,
    list: (params: Record<string, unknown> | undefined) =>
      ['threads', 'list', params] as const,
    detail: (id: string) => ['threads', 'detail', id] as const,
  },

  // ── Recommendations ────────────────────────────────────
  recommendations: {
    all: ['recommendations'] as const,
    home: () => ['recommendations', 'home'] as const,
    topics: () => ['recommendations', 'topics'] as const,
    affinities: () => ['recommendations', 'affinities'] as const,
  },

  // ── User Prefs ─────────────────────────────────────────
  userPrefs: {
    all: ['user-prefs'] as const,
    topics: () => ['user-prefs', 'topics'] as const,
    affinities: () => ['user-prefs', 'affinities'] as const,
    recommendationConfig: () => ['user-prefs', 'recommendation-config'] as const,
    // 推荐质量打标（金标采样与汇总）
    labelSample: () => ['user-prefs', 'label-sample'] as const,
    labelSummary: () => ['user-prefs', 'label-summary'] as const,
  },

  // ── Sources ────────────────────────────────────────────
  sources: {
    all: ['sources'] as const,
    discovery: () => ['sources', 'discovery'] as const,
  },

  // ── Stats ──────────────────────────────────────────────
  stats: {
    all: ['stats'] as const,
  },

  // ── Feeds（RSS 机器出口）─────────────────────────────────
  feeds: {
    all: ['feeds'] as const,
    overview: () => ['feeds', 'overview'] as const,
  },

  // ── LLM 接入配置 ────────────────────────────────────────
  llm: {
    all: ['llm'] as const,
    config: () => ['llm', 'config'] as const,
    receipts: (page: number = 1) => ['llm', 'receipts', page] as const,
  },
}
