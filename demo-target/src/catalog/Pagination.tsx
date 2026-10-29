import { Link } from 'react-router-dom'

interface PaginationProps {
  page: number
  pageCount: number
}

/** Numbered page links for the catalogue grid. */
export function Pagination({ page, pageCount }: PaginationProps) {
  if (pageCount <= 1) return null
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1)

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

function pageHref(page: number): string {
  return `/shop?page=${page}`
}
