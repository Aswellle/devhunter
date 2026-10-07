// ── User Preferences & Recommendations ────────────────────
export interface UserTopic {
  id: string
  topic: string
  category: string
  weight: number
  created_at: string
  updated_at: string
}

export interface UserTopicCreate {
  topic: string
  category?: string
  weight?: number
}

export interface InteractionRecord {
  item_id: string
  interaction_type: 'view' | 'click' | 'dwell' | 'star' | 'share'
  dwell_seconds?: number
}

export interface RecommendedTopic {
  topic: string
  category: string
  score: number
}

export interface Item {
  id: string
  task_id: string
  task_name: string | null
  thread_id: string | null
  title: string
  url: string
  summary: string | null
  is_read: boolean
  is_starred: boolean
  fetched_at: string
  created_at: string
}

export interface RecommendedItem extends Item {
  recommendation_score: number
  recommendation_reasons?: RecommendationReason[]
}

export interface RecommendationReason {
  type: 'topic' | 'affinity' | 'recency' | 'engagement' | 'thread' | 'exploration'
  label: string
}

// ── Source Discovery ──────────────────────────────────────
export interface DiscoveryResult {
  url: string
  source_type: 'rss' | 'json' | 'html' | 'unknown'
  title: string
  description: string
  feed_url: string
  json_path: string
  list_selector: string
  title_selector: string
  link_selector: string
  summary_selector: string
  next_page_selector: string
  candidate_count: number
  sample_items: Array<{ title: string; url: string; summary: string }>
  errors: string[]
}

export interface PreviewResult {
  success: boolean
  items: Array<{ title: string; url: string; summary: string }>
  total_found: number
  error: string
  http_status: number
}

export interface TestResult {
  success: boolean
  transport_success: boolean
  parse_success: boolean
  semantic_success: boolean
  http_status: number
  items_found: number
  field_coverage: number
  errors: string[]
  warnings: string[]
}

// ── Task 采集任务 ────────────────────────────────────────
export interface Task {
  id: string
  name: string
  source_url: string
  template_id: string | null
  selector_list: string
  selector_title: string
  selector_link: string
  selector_summary: string | null
  selector_next_page: string | null
  keywords: string[]
  cron_expression: string
  status: 'active' | 'paused' | 'error'
  consecutive_failures: number
  consecutive_empty: number
  last_executed_at: string | null
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  name: string
  source_url: string
  template_id?: string | null
  selector_list: string
  selector_title: string
  selector_link: string
  selector_summary?: string | null
  selector_next_page?: string | null
  keywords: string[]
  cron_expression: string
}

export interface TaskUpdate extends Partial<TaskCreate> {
  status?: 'active' | 'paused'
}

// ── Thread 多平台聚合 ────────────────────────────────────────
export interface Thread {
  id: string
  title: string
  first_seen_at: string
  last_seen_at: string
  item_count: number
  platforms: string[]
  confidence?: string
  /** 派生热度：唯一来源计数 + 24h 半衰期 + 48h 窗口（app/threads/hotness.py） */
  hotness?: number
}

export interface ThreadWithItems extends Thread {
  items: Item[]
  /** 聚合画像：为什么聚为一个 Thread（规模/活跃度/匹配置信度） */
  stats?: ThreadStats
}

/** Thread 聚合画像，由后端从 items 推导（app/threads/stats.py） */
export interface ThreadStats {
  item_count: number
  platform_count: number
  platform_breakdown: { platform: string; count: number }[]
  recent_6h_count: number
  recent_24h_count: number
  span_hours: number | null
  /** 非种子条目数（种子 = 创建 Thread 的首条报道） */
  matched_item_count: number
  similarity_avg: number | null
  similarity_max: number | null
  confidence: 'high' | 'medium' | 'low' | null
  is_cross_platform: boolean
  hotness: number
}

// ── TaskExecution 执行记录 ────────────────────────────────
export interface TaskExecution {
  id: string
  task_id: string
  // 与后端执行状态机一致：running 为执行中占位行，interrupted 为进程重启恢复标记
  status: 'success' | 'failure' | 'warning' | 'running' | 'interrupted'
  items_fetched: number
  items_new: number
  duration_ms: number
  error_message: string | null
  executed_at: string
}

/** POST /api/items/threads/recompute 响应 */
export interface ThreadRecomputeResult {
  items: number
  threads: number
  duration_ms: number
  window_hours: number
}

// ── RSS 机器出口 ──────────────────────────────────────────
export interface FeedInfo {
  task_id: string
  task_name: string
  url: string
}

/** GET /api/rss/feeds 响应：订阅地址清单 + 能力令牌 */
export interface FeedOverview {
  token: string
  base_url: string
  all_url: string
  feeds: FeedInfo[]
}

// ── 阅读亲缘度（我的画像）─────────────────────────────────
export interface AffinityEntry {
  id: string
  affinity_type: string
  affinity_value: string
  affinity_score: number
  interaction_count: number
  last_interacted_at: string
  updated_at: string
  /** 后端解析后的展示名：task 行原始值是 task_id，platform 行按历史约定存任务名 */
  display_value: string | null
  /** 解析后的展示维度：task | keyword */
  display_type: string | null
}

// ── 通用分页响应 ──────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

// ── Source Template ──────────────────────────────────────
export interface SourceTemplate {
  id: string
  name: string
  description: string
  source_url: string
  selector_list: string
  selector_title: string
  selector_link: string
  selector_summary: string | null
  default_keywords: string[]
  recommended_cron: string
  category?: string
  subcategory?: string
}

// ── Auth ──────────────────────────────────────────────────
/** 登录响应体：JWT 只通过 httpOnly Cookie 下发（XSS 缓解），响应体不含 token */
export interface TokenResponse {
  ok: boolean
}

// ── 频率快捷选项 ──────────────────────────────────────────
