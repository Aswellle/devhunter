/**
 * StarredPage：收藏列表 + 自定义文件夹分组。
 *
 * - 文件夹可新建 / 重命名 / 删除（删除后条目回到"未分类"，收藏状态不变）
 * - 单条条目可在卡片内直接选择文件夹
 * - 勾选多条后可批量移入文件夹，或在批量操作中新建文件夹并移入
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { CheckCheck, Folder, FolderPlus, Pencil, Star, Trash2, X } from 'lucide-react'
import { clsx } from 'clsx'
import { itemsApi } from '../api/items'
import { starFoldersApi } from '../api/star_folders'
import { queryKeys } from '../api/queryKeys'
import { errorMessage } from '../api/client'
import { ItemCard } from '../components/items/ItemCard'
import { FolderDialog } from '../components/starred/FolderDialog'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Pagination } from '../components/ui/Pagination'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import type { StarFolder } from '../types'
import { usePageTitle } from '../hooks/usePageTitle'

const ALL = 'all'
const UNCATEGORIZED = 'none'
const PER_PAGE = 20

type DialogState =
  | { mode: 'create'; assignSelected: boolean }
  | { mode: 'rename'; folder: StarFolder }

export function StarredPage() {
  usePageTitle('收藏')
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [folderFilter, setFolderFilter] = useState<string>(ALL)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<StarFolder | null>(null)

  // 翻页/切换文件夹时滚动到顶部。布局滚动容器是 AppLayout 的 <main id="main-content">
  useEffect(() => {
    document.getElementById('main-content')?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [page, folderFilter])

  const { data: overview } = useQuery({
    queryKey: queryKeys.starFolders.overview(),
    queryFn: starFoldersApi.list,
    staleTime: 30_000,
  })
  const folders = useMemo(() => overview?.folders ?? [], [overview?.folders])

  const filterKey = folderFilter === ALL ? undefined : folderFilter
  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: queryKeys.items.starred(filterKey, page),
    queryFn: () =>
      itemsApi.list({
        starred: true,
        star_folder_id: filterKey,
        page,
        per_page: PER_PAGE,
      }),
    placeholderData: (prev) => prev,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: queryKeys.starFolders.all })
    qc.invalidateQueries({ queryKey: queryKeys.items.starredAll })
    qc.invalidateQueries({ queryKey: queryKeys.items.all })
  }

  const createMutation = useMutation({
    mutationFn: async ({ name, itemIds }: { name: string; itemIds: string[] }) => {
      const folder = await starFoldersApi.create(name)
      if (itemIds.length) await starFoldersApi.assign(itemIds, folder.id)
      return folder
    },
    onSuccess: (folder, vars) => {
      invalidate()
      setDialog(null)
      if (vars.itemIds.length) {
        setSelectedIds(new Set())
        toast.success(`已新建「${folder.name}」并移入 ${vars.itemIds.length} 条`)
      } else {
        setFolderFilter(folder.id)
        setPage(1)
        toast.success(`已新建文件夹「${folder.name}」`)
      }
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '新建文件夹失败')),
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      starFoldersApi.rename(id, name),
    onSuccess: () => {
      invalidate()
      setDialog(null)
      toast.success('文件夹已重命名')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '重命名失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: (folderId: string) => starFoldersApi.remove(folderId),
    onSuccess: (_, folderId) => {
      invalidate()
      if (folderFilter === folderId) {
        setFolderFilter(ALL)
        setPage(1)
      }
      setDeleteTarget(null)
      toast.success('文件夹已删除，其中的收藏已回到未分类')
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '删除失败')),
  })

  const assignMutation = useMutation({
    mutationFn: ({
      ids,
      folderId,
    }: {
      ids: string[]
      folderId: string | null
      batch: boolean
    }) => starFoldersApi.assign(ids, folderId),
    onSuccess: (result, vars) => {
      invalidate()
      if (vars.batch) setSelectedIds(new Set())
      toast.success(
        vars.folderId
          ? `已移动 ${result.updated} 条收藏`
          : `已移出文件夹 ${result.updated} 条`,
      )
    },
    onError: (e: unknown) => toast.error(errorMessage(e, '移动失败')),
  })

  const selectFolder = (next: string) => {
    setFolderFilter(next)
    setPage(1)
    setSelectedIds(new Set())
  }

  const toggleSelect = (itemId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(itemId)) next.delete(itemId)
      else next.add(itemId)
      return next
    })
  }

  const pageIds = data?.items.map((item) => item.id) ?? []
  const allPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id))
  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allPageSelected) pageIds.forEach((id) => next.delete(id))
      else pageIds.forEach((id) => next.add(id))
      return next
    })
  }

  const activeFolder = folders.find((f) => f.id === folderFilter)
  const listTitle =
    folderFilter === ALL
      ? '全部收藏'
      : folderFilter === UNCATEGORIZED
        ? '未分类'
        : activeFolder?.name ?? '文件夹'
  const listCount = data?.total ?? 0
  const hasFilter = folderFilter !== ALL

  const folderRowClass = (active: boolean) =>
    clsx(
      'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors whitespace-nowrap',
      active
        ? 'bg-primary-50 text-primary-700 font-medium'
        : 'text-gray-600 hover:bg-gray-50',
    )

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
          已收藏
        </h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {overview
            ? `共 ${overview.total_starred} 条收藏，${folders.length} 个文件夹`
            : '用文件夹整理你的收藏'}
        </p>
      </div>

      <div className="md:flex md:items-start md:gap-6">
        {/* 文件夹侧栏（移动端横向滚动） */}
        <aside className="mb-4 md:mb-0 md:w-56 shrink-0">
          <div className="card p-2 md:sticky md:top-4">
            <div className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible">
              <button
                type="button"
                onClick={() => selectFolder(ALL)}
                className={folderRowClass(folderFilter === ALL)}
              >
                <Star className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="flex-1 text-left">全部收藏</span>
                <span className="text-xs text-gray-400">
                  {overview?.total_starred ?? ''}
                </span>
              </button>
              <button
                type="button"
                onClick={() => selectFolder(UNCATEGORIZED)}
                className={folderRowClass(folderFilter === UNCATEGORIZED)}
              >
                <Folder className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="flex-1 text-left">未分类</span>
                <span className="text-xs text-gray-400">
                  {overview?.uncategorized_count ?? ''}
                </span>
              </button>
            </div>

            <div className="hidden md:block my-2 border-t border-gray-100" />
            <div className="hidden md:block px-2.5 pb-1 text-[11px] font-medium text-gray-400">
              我的文件夹
            </div>
            <div className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible mt-1 md:mt-0">
              {folders.map((folder) => {
                const active = folderFilter === folder.id
                return (
                  <div key={folder.id} className="group flex items-center shrink-0">
                    <button
                      type="button"
                      onClick={() => selectFolder(folder.id)}
                      className={clsx(folderRowClass(active), 'flex-1 min-w-0')}
                      title={folder.name}
                    >
                      <Folder className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="flex-1 text-left truncate">{folder.name}</span>
                      <span className="text-xs text-gray-400">{folder.item_count}</span>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        createMutation.reset()
                        renameMutation.reset()
                        setDialog({ mode: 'rename', folder })
                      }}
                      className="p-1 rounded text-gray-300 hover:text-gray-600 hover:bg-gray-100 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      aria-label={`重命名文件夹 ${folder.name}`}
                      title="重命名"
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(folder)}
                      className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                      aria-label={`删除文件夹 ${folder.name}`}
                      title="删除文件夹"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </div>
                )
              })}
            </div>

            <button
              type="button"
              onClick={() => {
                createMutation.reset()
                renameMutation.reset()
                setDialog({ mode: 'create', assignSelected: false })
              }}
              className="mt-2 flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-primary-600 hover:bg-primary-50 transition-colors whitespace-nowrap"
            >
              <FolderPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
              新建文件夹
            </button>
          </div>
        </aside>

        {/* 收藏列表 */}
        <section className="flex-1 min-w-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-gray-900 truncate">
                {listTitle}
                <span className="ml-2 text-sm font-normal text-gray-400">
                  {listCount} 条
                </span>
              </h2>
              {hasFilter && (
                <p className="text-xs text-gray-400 mt-0.5">
                  仅在收藏中整理，取消收藏后条目会从此文件夹消失，重新收藏会自动回来
                </p>
              )}
            </div>
            {pageIds.length > 0 && (
              <button
                type="button"
                onClick={toggleSelectAll}
                className="btn-ghost btn-sm text-xs shrink-0"
              >
                <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" />
                {allPageSelected ? '取消全选' : '全选本页'}
              </button>
            )}
          </div>

          {isLoading && !data ? (
            <div className="flex justify-center py-20">
              <Spinner className="h-8 w-8" />
            </div>
          ) : isError ? (
            <Empty
              title="加载失败"
              description="收藏列表加载出错，请检查网络连接后重试"
              action={
                <button onClick={() => refetch()} className="btn-primary">
                  重试
                </button>
              }
            />
          ) : !data?.items.length ? (
            folderFilter === UNCATEGORIZED ? (
              <Empty
                title="没有未分类的收藏"
                description="所有收藏都已归入文件夹"
                action={
                  <button onClick={() => selectFolder(ALL)} className="btn-ghost">
                    查看全部收藏
                  </button>
                }
              />
            ) : hasFilter ? (
              <Empty
                title="这个文件夹还是空的"
                description="切换到「全部收藏」，勾选条目后使用「移动到…」把它收纳进来"
                action={
                  <button onClick={() => selectFolder(ALL)} className="btn-ghost">
                    去全部收藏
                  </button>
                }
              />
            ) : (
              <Empty
                title="暂无收藏"
                description="在「采集结果」页面点击条目右侧的 ☆ 图标即可收藏"
              />
            )
          ) : (
            <div className={isFetching ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
              <div className="space-y-3">
                {data.items.map((item) => (
                  <ItemCard
                    key={item.id}
                    item={item}
                    selectable
                    selected={selectedIds.has(item.id)}
                    onToggleSelect={toggleSelect}
                    folderControl={
                      <label
                        className="inline-flex items-center gap-1 text-gray-500"
                        title="移动到文件夹"
                      >
                        <Folder className="h-3 w-3" aria-hidden="true" />
                        <select
                          value={item.star_folder_id ?? ''}
                          onChange={(e) =>
                            assignMutation.mutate({
                              ids: [item.id],
                              folderId: e.target.value || null,
                              batch: false,
                            })
                          }
                          disabled={assignMutation.isPending}
                          aria-label={`将「${item.title}」移动到文件夹`}
                          className="max-w-[9rem] truncate rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-600 focus:border-primary-500 focus:outline-none"
                        >
                          <option value="">未分类</option>
                          {folders.map((folder) => (
                            <option key={folder.id} value={folder.id}>
                              {folder.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    }
                  />
                ))}
              </div>
              <Pagination
                page={page}
                total={data.total}
                perPage={data.per_page}
                onChange={setPage}
              />
            </div>
          )}

          {/* 批量操作条 */}
          {selectedIds.size > 0 && (
            <div className="sticky bottom-4 z-30 flex justify-center pt-4">
              <div className="flex flex-wrap items-center justify-center gap-2 px-4 py-3 bg-gray-900 text-white rounded-xl shadow-2xl">
                <span className="text-sm font-medium" aria-live="polite">
                  已选 <b>{selectedIds.size}</b> 条
                </span>
                <div className="w-px h-5 bg-gray-700" />
                <select
                  value=""
                  disabled={assignMutation.isPending}
                  onChange={(e) => {
                    const value = e.target.value
                    if (!value) return
                    if (value === '__new__') {
                      createMutation.reset()
                      setDialog({ mode: 'create', assignSelected: true })
                      return
                    }
                    assignMutation.mutate({
                      ids: [...selectedIds],
                      folderId: value === '__none__' ? null : value,
                      batch: true,
                    })
                  }}
                  aria-label="移动所选收藏到文件夹"
                  className="rounded-lg bg-gray-800 px-2.5 py-1.5 text-sm text-white border border-gray-700 focus:border-primary-500 focus:outline-none"
                >
                  <option value="" disabled>
                    移动到…
                  </option>
                  <option value="__none__">移出到未分类</option>
                  {folders.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.name}（{folder.item_count}）
                    </option>
                  ))}
                  <option value="__new__">＋ 新建文件夹并移入</option>
                </select>
                <button
                  type="button"
                  onClick={() => setSelectedIds(new Set())}
                  aria-label="取消选择"
                  className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      {dialog?.mode === 'create' && (
        <FolderDialog
          title={
            dialog.assignSelected
              ? `新建文件夹并移入 ${selectedIds.size} 条`
              : '新建收藏文件夹'
          }
          confirmText="创建"
          pending={createMutation.isPending}
          error={
            createMutation.error ? errorMessage(createMutation.error, '新建失败') : null
          }
          onCancel={() => setDialog(null)}
          onSubmit={(name) =>
            createMutation.mutate({
              name,
              itemIds: dialog.assignSelected ? [...selectedIds] : [],
            })
          }
        />
      )}

      {dialog?.mode === 'rename' && (
        <FolderDialog
          title="重命名文件夹"
          initialName={dialog.folder.name}
          confirmText="保存"
          pending={renameMutation.isPending}
          error={
            renameMutation.error ? errorMessage(renameMutation.error, '重命名失败') : null
          }
          onCancel={() => setDialog(null)}
          onSubmit={(name) =>
            renameMutation.mutate({ id: dialog.folder.id, name })
          }
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={`删除文件夹「${deleteTarget.name}」？`}
          message="文件夹中的收藏会回到「未分类」，不会被取消收藏。"
          confirmText="删除文件夹"
          variant="danger"
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
