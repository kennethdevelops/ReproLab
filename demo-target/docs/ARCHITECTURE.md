# Northwind Goods storefront — developer notes

Small React single-page store served by a plain Node HTTP server. All data is synthetic.

## Layout

- `src/pages/` — route components: `ShopPage` (`/shop`), `CartPage` (`/cart`), `CheckoutPage` (`/checkout`), `ProfilePage` (`/account/profile`).
- `src/catalog/` — product loading (`useProducts`), sorting, `Pagination`.
- `src/cart/` — `CartContext` (cart lines, quantity changes), `storage.ts` (localStorage persistence), `useCartTotals` (joins lines with products, computes subtotal).
- `src/checkout/` — `useCoupon` (validates codes with the server and tracks the applied discount).
- `src/lib/` — API client and money helpers. Prices are integer cents.
- `server/` — HTTP server (`index.mjs`), seed data (`data.mjs`), coupon validation (`coupons.mjs`), profile store (`profile.mjs`).

## State and persistence

| State | Where it lives |
|---|---|
| Cart lines | `localStorage` key `northwind.cart.v1` via `src/cart/storage.ts` |
| Catalogue filter and page | URL query string (`?category=Kitchen&page=2`) |
| Sort order | `ShopPage` component state |
| Applied coupon | `useCoupon` hook state |
| Shipping method | `CheckoutPage` component state |
| Profile | Server memory (`server/profile.mjs`), reset on restart |

## API

| Route | Notes |
|---|---|
| `GET /api/products` | Full catalogue (32 products, 4 categories) |
| `GET /api/shipping-options` | Standard, express, pickup |
| `POST /api/coupons/validate` | Body `{ "code": "SAVE10" }` → `{ valid, code, percentOff, message }` |
| `GET /api/profile`, `PUT /api/profile` | Synthetic single user |
| `POST /__admin/reset` | Operator only; requires `X-Admin-Token` |

## Coupons

`SAVE10` (10%), `WELCOME5` (5%). `SUMMER23` expired on 2023-08-31.

## Accessible selectors

Controls use visible labels and roles: "Category" and "Sort by" selects, "Add <product> to cart" buttons, the "Pagination" navigation with "Page N" links, "Quantity for <product>" inputs with "Increase/Decrease quantity of <product>" buttons, "Coupon code" input with an "Apply coupon" button, and the "Order summary" region with `summary-subtotal`, `summary-discount`, `summary-shipping` and `summary-total` test IDs.
