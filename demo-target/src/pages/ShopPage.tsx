import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useCart } from '../cart/CartContext'
import { Pagination } from '../catalog/Pagination'
import { PAGE_SIZE, sortProducts, useProducts, type SortKey } from '../catalog/useProducts'
import { formatCents } from '../lib/money'

const CATEGORIES = ['All', 'Kitchen', 'Outdoor', 'Office', 'Home']

export function ShopPage() {
  const { data: products, error } = useProducts()
  const { add } = useCart()
  const [searchParams, setSearchParams] = useSearchParams()
  const [sort, setSort] = useState<SortKey>('featured')
  const [lastAdded, setLastAdded] = useState<string | null>(null)

  const category = searchParams.get('category') ?? 'All'
  const page = Math.max(1, Number(searchParams.get('page')) || 1)

  const filtered = (products ?? []).filter((p) => category === 'All' || p.category === category)
  const sorted = sortProducts(filtered, sort)
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const visible = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function changeCategory(next: string) {
    const params = new URLSearchParams()
    if (next !== 'All') params.set('category', next)
    setSearchParams(params)
  }

  return (
    <section>
      <div className="page-head">
        <h1>Shop</h1>
        <div className="filters">
          <label>
            Category
            <select value={category} onChange={(e) => changeCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="featured">Featured</option>
              <option value="price-asc">Price: low to high</option>
              <option value="price-desc">Price: high to low</option>
              <option value="name">Name</option>
            </select>
          </label>
        </div>
      </div>

      {error && <p role="alert">{error}</p>}
      {!products && !error && <p role="status">Loading products…</p>}
      {lastAdded && (
        <p role="status" className="toast">
          Added {lastAdded} to cart.
        </p>
      )}

      <ul className="grid" aria-label="Products">
        {visible.map((product) => (
          <li key={product.id} className="card" data-testid="product-card">
            <div className="thumb" aria-hidden="true">
              {product.name.slice(0, 1)}
            </div>
            <h2>{product.name}</h2>
            <p className="muted" data-testid="product-category">
              {product.category}
            </p>
            <p className="price">{formatCents(product.priceCents)}</p>
            <button
              type="button"
              onClick={() => {
                add(product.id)
                setLastAdded(product.name)
              }}
              aria-label={`Add ${product.name} to cart`}
            >
              Add to cart
            </button>
          </li>
        ))}
      </ul>

      <Pagination page={page} pageCount={pageCount} />
    </section>
  )
}
