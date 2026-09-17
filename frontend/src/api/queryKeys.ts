/**
 * F2: Query Key 规范化 — 统一的 query key 工厂。
 *
 * 所有 TanStack Query 的 key 通过此工厂生成，确保：
 * - invalidate 时能精确匹配
 * - 命名风格一致
 * - 避免 key 散落在各处导致遗漏 invalidate
 */

export const queryKeys = {
  // ── Items ──────────────────────────────────────────────
  items: {
    all: ['items'] as const,
    grouped: (filters: Record<string, unknown> | undefined) =>
      ['items', 'grouped', filters] as const,
    counts: () => ['items', 'counts'] as const,
    detail: (id: string) => ['items', 'detail', id] as const,
    starred: () => ['items', 'starred'] as const,
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
}
