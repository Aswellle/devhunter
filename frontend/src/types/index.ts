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

// ── Item 采集结果 ─────────────────────────────────────────
export interface Item {
  id: string
  task_id: string
  task_name: string | null
  thread_id: string | null  // 所属 Thread（多平台聚合）
  title: string
  url: string
  summary: string | null
  is_read: boolean
  is_starred: boolean
  fetched_at: string
  created_at: string
}

// ── Thread 多平台聚合 ────────────────────────────────────────
export interface Thread {
  id: string
  title: string           // 规范化 Thread 标题（最完整的那个）
  first_seen_at: string  // 首次出现
  last_seen_at: string  // 最近一次出现
  item_count: number     // 包含的 Items 数量
  platforms: string[]   // 来源平台列表
}

export interface ThreadWithItems extends Thread {
  items: Item[]  // Thread 内的所有 Items
}

// ── TaskExecution 执行记录 ────────────────────────────────
export interface TaskExecution {
  id: string
  task_id: string
  status: 'success' | 'failure' | 'warning'
  items_fetched: number
  items_new: number
  duration_ms: number
  error_message: string | null
  executed_at: string
}

// ── 通用分页响应 ──────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}

// ── 预设模板 ──────────────────────────────────────────────
export interface SourceTemplate {
  id: string
  name: string
  source_url: string
  selector_list: string
  selector_title: string
  selector_link: string
  selector_summary: string | null
  description: string
  recommended_cron: string
}

// ── Auth ──────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string
  token_type: string
}

// ── 频率快捷选项 ──────────────────────────────────────────
export const CRON_PRESETS = [
  { label: '每 30 分钟', value: '*/30 * * * *' },
  { label: '每小时',     value: '0 * * * *' },
  { label: '每 6 小时',  value: '0 */6 * * *' },
  { label: '每天 9:00',  value: '0 9 * * *' },
] as const
