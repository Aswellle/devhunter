import client from './client'
import type { RecommendedItem, RecommendedTopic, UserTopic, UserTopicCreate } from '../types'
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
}
