import { Link } from 'react-router-dom'
import { useCart } from '../cart/CartContext'
import { useCartTotals } from '../cart/useCartTotals'
import { useProducts } from '../catalog/useProducts'
import { formatCents } from '../lib/money'

export function CartPage() {
  const { data: products } = useProducts()
  const { lines, setQuantity, remove } = useCart()
  const { items, subtotalCents } = useCartTotals(products)

  if (products && items.length === 0) {
    return (
      <section>
        <h1>Your cart</h1>
        <p>
          Your cart is empty. <Link to="/shop">Continue shopping</Link>
        </p>
      </section>
    )
  }

  return (
    <section>
      <h1>Your cart</h1>
      <table className="cart-table">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col">Price</th>
            <th scope="col">Quantity</th>
            <th scope="col">Total</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map(({ product }) => {
            const quantity = lines.find((l) => l.productId === product.id)?.quantity ?? 0
            return (
            <tr key={product.id}>
              <td>{product.name}</td>
              <td>{formatCents(product.priceCents)}</td>
              <td>
                <div className="qty">
                  <button
                    type="button"
                    aria-label={`Decrease quantity of ${product.name}`}
                    onClick={() => setQuantity(product.id, quantity - 1)}
                  >
                    −
                  </button>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={quantity}
                    aria-label={`Quantity for ${product.name}`}
                    onChange={(e) => setQuantity(product.id, Number(e.target.value))}
                  />
                  <button
                    type="button"
                    aria-label={`Increase quantity of ${product.name}`}
                    onClick={() => setQuantity(product.id, quantity + 1)}
                  >
                    +
                  </button>
                </div>
              </td>
              <td>{formatCents(product.priceCents * quantity)}</td>
              <td>
                <button type="button" className="link" onClick={() => remove(product.id)}>
                  Remove
                </button>
              </td>
            </tr>
            )
          })}
        </tbody>
      </table>
      <div className="summary-row" data-testid="cart-subtotal">
        <span>Subtotal</span>
        <strong>{formatCents(subtotalCents)}</strong>
      </div>
      <Link to="/checkout" className="button">
        Proceed to checkout
      </Link>
    </section>
  )
}
