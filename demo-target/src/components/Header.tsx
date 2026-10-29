import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useCart } from '../cart/CartContext'

export function Header() {
  const { lines } = useCart()
  const [menuOpen, setMenuOpen] = useState(false)
  const count = lines.reduce((n, l) => n + l.quantity, 0)

  return (
    <header className="site-header">
      <Link to="/shop" className="brand">
        Northwind Goods
      </Link>
      <button
        type="button"
        className="menu-toggle"
        aria-expanded={menuOpen}
        aria-controls="site-nav"
        onClick={() => setMenuOpen((o) => !o)}
      >
        Menu
      </button>
      <nav id="site-nav" aria-label="Store" className={menuOpen ? 'open' : ''}>
        <NavLink to="/shop" onClick={() => setMenuOpen(false)}>
          Shop
        </NavLink>
        <NavLink to="/account/profile" onClick={() => setMenuOpen(false)}>
          Profile
        </NavLink>
        <NavLink to="/cart" onClick={() => setMenuOpen(false)}>
          Cart <span aria-label={`${count} items in cart`}>({count})</span>
        </NavLink>
      </nav>
    </header>
  )
}
