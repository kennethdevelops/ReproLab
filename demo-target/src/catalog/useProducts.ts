import { useEffect, useState } from 'react'
import { api, type Product, type ShippingOption } from '../lib/api'

interface Loadable<T> {
  data: T | undefined
  error: string | null
}

function useLoad<T>(loader: () => Promise<T>): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ data: undefined, error: null })
  useEffect(() => {
    let active = true
    loader()
      .then((data) => active && setState({ data, error: null }))
      .catch(() => active && setState({ data: undefined, error: 'Could not load data.' }))
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return state
}

export const useProducts = () => useLoad<Product[]>(api.products)
export const useShippingOptions = () => useLoad<ShippingOption[]>(api.shippingOptions)

export const PAGE_SIZE = 6

export type SortKey = 'featured' | 'price-asc' | 'price-desc' | 'name'

export function sortProducts(products: Product[], sort: SortKey): Product[] {
  const copy = [...products]
  switch (sort) {
    case 'price-asc':
      return copy.sort((a, b) => a.priceCents - b.priceCents)
    case 'price-desc':
      return copy.sort((a, b) => b.priceCents - a.priceCents)
    case 'name':
      return copy.sort((a, b) => a.name.localeCompare(b.name))
    default:
      return copy
  }
}
