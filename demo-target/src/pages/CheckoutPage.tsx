import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useCart } from '../cart/CartContext'
import { useCartTotals } from '../cart/useCartTotals'
import { useProducts, useShippingOptions } from '../catalog/useProducts'
import { useCoupon } from '../checkout/useCoupon'
import { formatCents, percentOf } from '../lib/money'

export function CheckoutPage() {
  const { data: products } = useProducts()
  const { data: shippingOptions } = useShippingOptions()
  const { clear } = useCart()
  const { items, subtotalCents } = useCartTotals(products)
  const coupon = useCoupon()
  const [code, setCode] = useState('')
  const [shippingId, setShippingId] = useState('standard')
  const [placed, setPlaced] = useState(false)

  const shipping = shippingOptions?.find((o) => o.id === shippingId)
  const discountCents = coupon.applied ? percentOf(subtotalCents, coupon.applied.percentOff) : 0
  const totalCents = subtotalCents - discountCents + (shipping?.priceCents ?? 0)

  async function onApply(e: FormEvent) {
    e.preventDefault()
    await coupon.apply(code)
    setCode('')
  }

  if (placed) {
    return (
      <section>
        <h1>Order placed</h1>
        <p role="status">
          Thank you! This is a demo store, so no payment was taken and nothing will ship.
        </p>
        <Link to="/shop">Back to shop</Link>
      </section>
    )
  }

  if (products && items.length === 0) {
    return (
      <section>
        <h1>Checkout</h1>
        <p>
          Your cart is empty. <Link to="/shop">Continue shopping</Link>
        </p>
      </section>
    )
  }

  return (
    <section className="checkout">
      <h1>Checkout</h1>
      <div className="checkout-grid">
        <div>
          <h2>Items</h2>
          <ul className="line-items">
            {items.map(({ product, quantity, lineTotalCents }) => (
              <li key={product.id}>
                <span>
                  {product.name} × {quantity}
                </span>
                <span>{formatCents(lineTotalCents)}</span>
              </li>
            ))}
          </ul>

          <h2>Shipping</h2>
          <label>
            Shipping method
            <select value={shippingId} onChange={(e) => setShippingId(e.target.value)}>
              {shippingOptions?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label} — {formatCents(o.priceCents)}
                </option>
              ))}
            </select>
          </label>

          <h2>Coupon</h2>
          {coupon.applied ? (
            <p className="applied">
              Coupon <strong>{coupon.applied.code}</strong> applied.{' '}
              <button type="button" className="link" onClick={coupon.remove}>
                Remove coupon
              </button>
            </p>
          ) : (
            <form onSubmit={onApply} className="coupon-form">
              <label>
                Coupon code
                <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={32} />
              </label>
              <button type="submit" disabled={coupon.pending || !code.trim()}>
                Apply coupon
              </button>
            </form>
          )}
          {coupon.message && <p role="status">{coupon.message}</p>}
          {coupon.error && (
            <p role="alert" className="error">
              {coupon.error}
            </p>
          )}
        </div>

        <aside aria-label="Order summary" className="summary">
          <h2>Order summary</h2>
          <dl>
            <div>
              <dt>Subtotal</dt>
              <dd data-testid="summary-subtotal">{formatCents(subtotalCents)}</dd>
            </div>
            {coupon.applied && (
              <div>
                <dt>Discount ({coupon.applied.code})</dt>
                <dd data-testid="summary-discount">−{formatCents(discountCents)}</dd>
              </div>
            )}
            <div>
              <dt>Shipping</dt>
              <dd data-testid="summary-shipping">{formatCents(shipping?.priceCents ?? 0)}</dd>
            </div>
            <div className="total">
              <dt>Total</dt>
              <dd data-testid="summary-total">{formatCents(totalCents)}</dd>
            </div>
          </dl>
          <button
            type="button"
            onClick={() => {
              clear()
              setPlaced(true)
            }}
          >
            Place order
          </button>
        </aside>
      </div>
    </section>
  )
}
