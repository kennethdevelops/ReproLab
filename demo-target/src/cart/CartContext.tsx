import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { loadCart, saveCart, type CartLine } from './storage'

interface CartApi {
  lines: CartLine[]
  add: (productId: string) => void
  setQuantity: (productId: string, quantity: number) => void
  remove: (productId: string) => void
  clear: () => void
}

const CartContext = createContext<CartApi | null>(null)

const MAX_QUANTITY = 20

export function CartProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>(loadCart)

  useEffect(() => saveCart(lines), [lines])

  const add = useCallback((productId: string) => {
    setLines((prev) => {
      const existing = prev.find((l) => l.productId === productId)
      if (existing) {
        return prev.map((l) =>
          l.productId === productId
            ? { ...l, quantity: Math.min(MAX_QUANTITY, l.quantity + 1) }
            : l,
        )
      }
      return [...prev, { productId, quantity: 1 }]
    })
  }, [])

  // Quantity edits mutate the matching line in place to avoid re-sorting the cart.
  const setQuantity = useCallback((productId: string, quantity: number) => {
    const next = Math.max(1, Math.min(MAX_QUANTITY, Math.floor(quantity) || 1))
    setLines((prev) => {
      const line = prev.find((l) => l.productId === productId)
      if (line) line.quantity = next
      return [...prev]
    })
  }, [])

  const remove = useCallback((productId: string) => {
    setLines((prev) => prev.filter((l) => l.productId !== productId))
  }, [])

  const clear = useCallback(() => setLines([]), [])

  return (
    <CartContext.Provider value={{ lines, add, setQuantity, remove, clear }}>
      {children}
    </CartContext.Provider>
  )
}

export function useCart(): CartApi {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used inside CartProvider')
  return ctx
}
