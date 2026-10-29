import { COUPONS } from './data.mjs'

/**
 * Validate a coupon code against the catalogue of active promotions.
 * Returns { valid, code, percentOff, message }.
 */
export function validateCoupon(rawCode, today = new Date()) {
  const code = String(rawCode ?? '').trim().toUpperCase()
  if (!code) return { valid: false, code, percentOff: 0, message: 'Enter a coupon code.' }

  const coupon = COUPONS.find((c) => c.code === code)
  if (!coupon) return { valid: false, code, percentOff: 0, message: 'This coupon code is not recognised.' }

  const expires = new Date(`${coupon.expiresOn}T23:59:59Z`)
  if (expires < today) {
    return { valid: false, code, percentOff: 0, message: `This coupon expired on ${coupon.expiresOn}.` }
  }
  return { valid: true, code, percentOff: coupon.percentOff, message: `${coupon.percentOff}% discount applied.` }
}
