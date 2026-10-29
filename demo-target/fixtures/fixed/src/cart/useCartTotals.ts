// FIXED VARIANT (evaluation fixture, never indexed): D02 stale subtotal.
import { useMemo } from 'react'
import type { Product } from '../../../../src/lib/api'
import { useCart } from '../../../../src/cart/CartContext'

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

export function useCartTotals(products: Product[] | undefined): CartTotals {
  const { lines } = useCart()
  // Depend on the quantities themselves, not just the number of lines.
  const signature = lines.map((l) => `${l.productId}:${l.quantity}`).join(',')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => computeTotals(lines, products), [signature, products])
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
