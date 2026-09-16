import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { itemsApi } from '../api/items'
import { ItemCard } from '../components/items/ItemCard'
import { Pagination } from '../components/ui/Pagination'
import { Spinner } from '../components/ui/Spinner'
import { Empty } from '../components/ui/Empty'
import { Star } from 'lucide-react'

export function StarredPage() {
  const [page, setPage] = useState(1)

  const { data, isLoading, isFetching, isError, refetch } = useQuery({
    queryKey: ['items-starred', page],
    queryFn: () => itemsApi.list({ starred: true, page, per_page: 20 }),
    placeholderData: (prev) => prev,
  })

  return (
    <div className="max-w-4xl mx-auto px-6 py-6">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
          已收藏
        </h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {data ? `共 ${data.total} 条收藏` : '加载中…'}
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Spinner className="h-8 w-8" />
        </div>
      ) : isError ? (
        // U3: page turning or a stale token previously surfaced this
        // failure as an identical "暂无收藏" empty state — indistinguishable
        // from a genuinely empty starred list.
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
        <Empty
          title="暂无收藏"
          description="在「采集结果」页面点击条目右侧的 ☆ 图标即可收藏"
        />
      ) : (
        // U11: placeholderData keeps the previous page's items visible
        // during a page turn with no visual cue that a fetch is in
        // flight — opacity dims the list while isFetching is true so a
        // slow page-turn doesn't look like the click did nothing.
        <div className={isFetching ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          <div className="space-y-3">
            {data.items.map((item) => (
              <ItemCard key={item.id} item={item} />
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
    </div>
  )
}
