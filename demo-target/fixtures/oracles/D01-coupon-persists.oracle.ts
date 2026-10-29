import { expect, test } from '@playwright/test'
import { addProductToCart, parseMoney } from './helpers'

// Steps titled "setup:" must pass on every build; only "oracle:" steps may fail on the buggy build.
test('D01 applied coupon persists after checkout reload', async ({ page }) => {
  await test.step('setup: apply SAVE10 at checkout', async () => {
    await addProductToCart(page, 'Cast Iron Skillet')
    await page.goto('/checkout')
    await page.getByLabel('Coupon code').fill('SAVE10')
    await page.getByRole('button', { name: 'Apply coupon' }).click()
    const discount = page.getByTestId('summary-discount')
    await expect(discount).toBeVisible()
    const subtotal = parseMoney(await page.getByTestId('summary-subtotal').textContent())
    expect(parseMoney(await discount.textContent())).toBe(Math.round(subtotal * 0.1))
  })

  await test.step('setup: reload checkout', async () => {
    await page.reload()
    await expect(page.getByTestId('summary-subtotal')).toBeVisible()
  })

  await test.step('oracle: discount still applied after reload', async () => {
    await expect(page.getByTestId('summary-discount')).toBeVisible()
    await expect(page.getByText('Coupon SAVE10 applied.')).toBeVisible()
  })
})
