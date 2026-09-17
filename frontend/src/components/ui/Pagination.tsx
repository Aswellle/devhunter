import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaginationProps {
  page: number
  total: number
  perPage: number
  onChange: (page: number) => void
}

export function Pagination({ page, total, perPage, onChange }: PaginationProps) {
  const totalPages = Math.ceil(total / perPage)
  if (totalPages <= 1) return null

  return (
    <nav aria-label="分页导航">
      <div className="flex items-center justify-between py-3">
        <p className="text-sm text-muted">
          共 <span className="font-medium">{total}</span> 条，第 {page}/{totalPages} 页
        </p>
        <div className="flex items-center gap-1" role="group">
          <button
            aria-label="上一页"
            className="btn-ghost p-1 rounded"
            disabled={page <= 1}
            onClick={() => onChange(page - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
            // Sliding window around current page
            let p = page - 2 + i
            if (p < 1) p = 1 + i
            if (p > totalPages) p = totalPages - (4 - i)
            return p
          })
            .filter((p, idx, arr) => p >= 1 && p <= totalPages && arr.indexOf(p) === idx)
            .map((p) => (
              <button
                key={p}
                aria-label={`第 ${p} 页`}
                aria-current={p === page ? 'page' : undefined}
                onClick={() => onChange(p)}
                className={`w-8 h-8 rounded text-sm font-medium transition-colors ${
                  p === page
                    ? 'bg-accent text-white'
                    : 'text-secondary hover:bg-hover'
                }`}
              >
                {p}
              </button>
            ))}
          <button
            aria-label="下一页"
            className="btn-ghost p-1 rounded"
            disabled={page >= totalPages}
            onClick={() => onChange(page + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </nav>
  )
}
