import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateCoupon } from '../server/coupons.mjs'
import { PRODUCTS } from '../server/data.mjs'
import { createProfileStore } from '../server/profile.mjs'

test('catalogue is deterministic and has 8 products per category', () => {
  assert.equal(PRODUCTS.length, 32)
  const counts = Object.groupBy(PRODUCTS, (p) => p.category)
  for (const items of Object.values(counts)) assert.equal(items.length, 8)
  assert.equal(new Set(PRODUCTS.map((p) => p.id)).size, 32)
  assert.ok(PRODUCTS.every((p) => Number.isInteger(p.priceCents) && p.priceCents > 0))
})

test('SAVE10 is a valid 10% coupon, case-insensitive', () => {
  assert.deepEqual(validateCoupon(' save10 ', new Date('2026-01-01')), {
    valid: true,
    code: 'SAVE10',
    percentOff: 10,
    message: '10% discount applied.',
  })
})

test('unknown and empty codes are rejected', () => {
  assert.equal(validateCoupon('NOPE').valid, false)
  assert.equal(validateCoupon('').valid, false)
})

test('profile store requires a display name', () => {
  const store = createProfileStore()
  assert.equal(store.update({ displayName: '' }).ok, false)
  const saved = store.update({ displayName: 'Sam', newsletter: true })
  assert.equal(saved.ok, true)
  assert.equal(store.get().displayName, 'Sam')
})
