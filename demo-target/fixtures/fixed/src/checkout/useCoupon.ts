// FIXED VARIANT (evaluation fixture, never indexed): D01 coupon lost on reload.
import { useCallback, useEffect, useState } from 'react'
import { api, type CouponResult } from '../../../../src/lib/api'

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

const COUPON_KEY = 'northwind.coupon.v1'

function loadCoupon(): AppliedCoupon | null {
  try {
    const raw = localStorage.getItem(COUPON_KEY)
    return raw ? (JSON.parse(raw) as AppliedCoupon) : null
  } catch {
    return null
  }
}

export function useCoupon(): CouponState {
  const [applied, setApplied] = useState<AppliedCoupon | null>(loadCoupon)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    try {
      if (applied) localStorage.setItem(COUPON_KEY, JSON.stringify(applied))
      else localStorage.removeItem(COUPON_KEY)
    } catch {
      // ignore storage errors
    }
  }, [applied])

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
