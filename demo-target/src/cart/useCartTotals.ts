import { useMemo } from 'react'
import type { Product } from '../lib/api'
import { useCart } from './CartContext'

export interface CartItem {
  product: Product
  quantity: number
  lineTotalCents: number
}

export interface CartTotals {
  items: CartItem[]
  itemCount: number
  subtotalCents: number
}

/**
 * Joins cart lines with catalogue data and computes the subtotal.
 * Memoised because the catalogue join runs on every render of the cart and checkout pages.
 */
export function useCartTotals(products: Product[] | undefined): CartTotals {
  const { lines } = useCart()

  // Recompute when products load or the set of lines changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const subtotal = useMemo(() => computeTotals(lines, products), [lines.length, products])

  return subtotal
}

function computeTotals(
  lines: { productId: string; quantity: number }[],
  products: Product[] | undefined,
): CartTotals {
  const byId = new Map((products ?? []).map((p) => [p.id, p]))
  const items: CartItem[] = []
  for (const line of lines) {
    const product = byId.get(line.productId)
    if (!product) continue
    items.push({ product, quantity: line.quantity, lineTotalCents: product.priceCents * line.quantity })
  }
  return {
    items,
    itemCount: items.reduce((n, i) => n + i.quantity, 0),
    subtotalCents: items.reduce((sum, i) => sum + i.lineTotalCents, 0),
  }
}
