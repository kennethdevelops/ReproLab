import { Navigate, Route, Routes } from 'react-router-dom'
import { Header } from './components/Header'
import { CartPage } from './pages/CartPage'
import { CheckoutPage } from './pages/CheckoutPage'
import { ProfilePage } from './pages/ProfilePage'
import { ShopPage } from './pages/ShopPage'

export default function App() {
  return (
    <>
      <Header />
      <main className="container">
        <Routes>
          <Route path="/" element={<Navigate to="/shop" replace />} />
          <Route path="/shop" element={<ShopPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/account/profile" element={<ProfilePage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
      <footer className="site-footer">
        Demo store with synthetic data. No real orders, payments or accounts.
      </footer>
    </>
  )
}
