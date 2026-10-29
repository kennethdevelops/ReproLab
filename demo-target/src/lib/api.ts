export interface Product {
  id: string
  name: string
  category: string
  priceCents: number
  rating: number
}

export interface ShippingOption {
  id: string
  label: string
  priceCents: number
}

export interface CouponResult {
  valid: boolean
  code: string
  percentOff: number
  message: string
}

export interface Profile {
  displayName: string
  email: string
  newsletter: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = (await response.json()) as T
  if (!response.ok && response.status !== 422) throw new Error(`Request failed: ${response.status}`)
  return body
}

export const api = {
  products: () => request<{ products: Product[] }>('/api/products').then((r) => r.products),
  shippingOptions: () =>
    request<{ options: ShippingOption[] }>('/api/shipping-options').then((r) => r.options),
  validateCoupon: (code: string) =>
    request<CouponResult>('/api/coupons/validate', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  getProfile: () => request<Profile>('/api/profile'),
  saveProfile: (profile: Partial<Profile>) =>
    request<{ ok: boolean; message?: string; profile?: Profile }>('/api/profile', {
      method: 'PUT',
      body: JSON.stringify(profile),
    }),
}
