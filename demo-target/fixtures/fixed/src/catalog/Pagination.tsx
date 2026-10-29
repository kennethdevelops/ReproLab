// FIXED VARIANT (evaluation fixture, never indexed): D05 category filter lost on pagination.
import { Link, useSearchParams } from 'react-router-dom'

interface PaginationProps {
  page: number
  pageCount: number
}

export function Pagination({ page, pageCount }: PaginationProps) {
  const [searchParams] = useSearchParams()
  if (pageCount <= 1) return null
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1)

  // Preserve every other active query parameter (category, etc.) when changing page.
  const pageHref = (p: number) => {
    const next = new URLSearchParams(searchParams)
    next.set('page', String(p))
    return `/shop?${next.toString()}`
  }

  return (
    <nav aria-label="Pagination" className="pagination">
      {page > 1 && (
        <Link to={pageHref(page - 1)} rel="prev">
          Previous
        </Link>
      )}
      {pages.map((p) =>
        p === page ? (
          <span key={p} aria-current="page" className="current">
            {p}
          </span>
        ) : (
          <Link key={p} to={pageHref(p)} aria-label={`Page ${p}`}>
            {p}
          </Link>
        ),
      )}
      {page < pageCount && (
        <Link to={pageHref(page + 1)} rel="next">
          Next
        </Link>
      )}
    </nav>
  )
}
