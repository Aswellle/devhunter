import client from './client'
import type { FeedOverview } from '../types'

export const feedsApi = {
  /** 获取 RSS 订阅地址清单与能力令牌（需登录） */
  getOverview: () =>
    client.get<FeedOverview>('/rss/feeds').then((r) => r.data),
}
