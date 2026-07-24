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

  const { data, isLoading } = useQuery({
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
      ) : !data?.items.length ? (
        <Empty
          title="暂无收藏"
          description="在「采集结果」页面点击条目右侧的 ☆ 图标即可收藏"
        />
      ) : (
        <>
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
        </>
      )}
    </div>
  )
}
