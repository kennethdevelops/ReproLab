import { useCallback, useState } from 'react'
import { api, type CouponResult } from '../lib/api'

export interface AppliedCoupon {
  code: string
  percentOff: number
}

export interface CouponState {
  applied: AppliedCoupon | null
  message: string | null
  error: string | null
  pending: boolean
  apply: (code: string) => Promise<void>
  remove: () => void
}

/** Checkout coupon state: validates codes with the server and tracks the applied discount. */
export function useCoupon(): CouponState {
  const [applied, setApplied] = useState<AppliedCoupon | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const apply = useCallback(async (code: string) => {
    setPending(true)
    setError(null)
    setMessage(null)
    try {
      const result: CouponResult = await api.validateCoupon(code)
      if (result.valid) {
        setApplied({ code: result.code, percentOff: result.percentOff })
        setMessage(result.message)
      } else {
        setError(result.message)
      }
    } catch {
      setError('Could not validate the coupon. Please try again.')
    } finally {
      setPending(false)
    }
  }, [])

  const remove = useCallback(() => {
    setApplied(null)
    setMessage(null)
    setError(null)
  }, [])

  return { applied, message, error, pending, apply, remove }
}
