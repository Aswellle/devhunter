import client from './client'
import type { StarFolder, StarFolderOverview } from '../types'

export const starFoldersApi = {
  list: () =>
    client.get<StarFolderOverview>('/star-folders').then((r) => r.data),

  create: (name: string) =>
    client.post<StarFolder>('/star-folders', { name }).then((r) => r.data),

  rename: (folderId: string, name: string) =>
    client
      .patch<StarFolder>(`/star-folders/${folderId}`, { name })
      .then((r) => r.data),

  remove: (folderId: string) =>
    client.delete(`/star-folders/${folderId}`).then((r) => r.data),

  /** 单个或批量把条目移入文件夹；folderId=null 表示移出到未分类 */
  assign: (itemIds: string[], folderId: string | null) =>
    client
      .patch<{ updated: number }>('/star-folders/assign', {
        item_ids: itemIds,
        folder_id: folderId,
      })
      .then((r) => r.data),
}
