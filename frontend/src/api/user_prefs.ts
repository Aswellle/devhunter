import client from './client'
import type { RecommendedItem, RecommendedTopic, UserTopic, UserTopicCreate, AffinityEntry, LabelSampleItem, LabelSummary } from '../types'
import type { PaginatedResponse } from '../types'

export const userPrefsApi = {
  // 获取个性化推荐（For You）
  getRecommendations: (params?: { limit?: number; exclude_read?: boolean }) =>
    client.get<PaginatedResponse<RecommendedItem>>('/user-prefs/recommendations', { params }).then((r) => r.data),

  // 获取用户主题偏好列表
  listTopics: () =>
    client.get<UserTopic[]>('/user-prefs/topics').then((r) => r.data),

  // 添加主题偏好
  addTopic: (data: UserTopicCreate) =>
    client.post<UserTopic>('/user-prefs/topics', data).then((r) => r.data),

  // 更新主题权重
  updateTopicWeight: (topic: string, weight: number) =>
    client.patch<UserTopic>(`/user-prefs/topics/${encodeURIComponent(topic)}`, { weight }).then((r) => r.data),

  // 删除主题偏好
  removeTopic: (topic: string) =>
    client.delete(`/user-prefs/topics/${encodeURIComponent(topic)}`),

  // 获取推荐主题（基于阅读历史）
  getRecommendedTopics: (params?: { limit?: number }) =>
    client.get<RecommendedTopic[]>('/user-prefs/topics/recommended', { params }).then((r) => r.data),

  // 记录用户交互
  recordInteraction: (data: { item_id: string; interaction_type: string; dwell_seconds?: number }) =>
    client.post('/user-prefs/interactions', data).then((r) => r.data),

  // 获取用户亲缘度
  getAffinities: () =>
    client.get<AffinityEntry[]>('/user-prefs/affinities').then((r) => r.data),

  // 获取推荐配置（四因子权重 + 推断的模式；从未保存过时返回打分引擎默认值）
  getRecommendationConfig: () =>
    client.get<{ preference_mode: string | null; weights: Record<string, number> }>(
      '/user-prefs/recommendations/config'
    ).then((r) => r.data),

  // 更新推荐配置
  updateRecommendationConfig: (data: { preference_mode?: string; weights?: Record<string, number> }) =>
    client.post('/user-prefs/recommendations/config', data).then((r) => r.data),

  // 记录负反馈
  recordFeedback: (data: { item_id: string; feedback_type: string; reason?: string }) =>
    client.post('/user-prefs/feedback', data).then((r) => r.data),

  // ── 推荐质量打标（金标）──
  // 采样待标注条目（带采样时的推荐得分快照）
  getLabelSample: (limit = 8) =>
    client.get<LabelSampleItem[]>('/user-prefs/recommendations/labels/sample', { params: { limit } }).then((r) => r.data),

  // 提交一条标注（感兴趣 / 不感兴趣；同一 item 重复提交为改判）
  submitLabel: (data: { item_id: string; label: boolean; sampled_score?: number }) =>
    client.post('/user-prefs/recommendations/labels', data).then((r) => r.data),

  // 打标汇总：计数 + 排序贴合度
  getLabelSummary: () =>
    client.get<LabelSummary>('/user-prefs/recommendations/labels/summary').then((r) => r.data),
}
