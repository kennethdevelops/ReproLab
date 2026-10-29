// Persists the shopping cart in localStorage so it survives reloads and new tabs.

export interface CartLine {
  productId: string
  quantity: number
}

const CART_KEY = 'northwind.cart.v1'

export function loadCart(): CartLine[] {
  try {
    const raw = localStorage.getItem(CART_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as CartLine[]
    return Array.isArray(parsed)
      ? parsed.filter((l) => typeof l.productId === 'string' && l.quantity > 0)
      : []
  } catch {
    return []
  }
}

export function saveCart(lines: CartLine[]): void {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(lines))
  } catch {
    // Storage full or disabled: the cart still works for this page view.
  }
}
