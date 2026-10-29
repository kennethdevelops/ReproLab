import { expect, test } from '@playwright/test'
import { addProductToCart, parseMoney } from './helpers'

test('D02 cart subtotal equals quantity times price after quantity change', async ({ page }) => {
  const subtotal = page.getByTestId('cart-subtotal')
  let unitPrice = 0

  await test.step('setup: one cutting board in cart', async () => {
    await addProductToCart(page, 'Bamboo Cutting Board')
    await page.goto('/cart')
    const row = page.getByRole('row', { name: /Bamboo Cutting Board/ })
    unitPrice = parseMoney(await row.getByRole('cell').nth(1).textContent())
    expect(parseMoney(await subtotal.textContent())).toBe(unitPrice)
  })

  await test.step('setup: increase quantity to 3', async () => {
    const increase = page.getByRole('button', { name: 'Increase quantity of Bamboo Cutting Board' })
    await increase.click()
    await increase.click()
    await expect(page.getByLabel('Quantity for Bamboo Cutting Board')).toHaveValue('3')
  })

  await test.step('oracle: subtotal equals 3 x unit price', async () => {
    await expect
      .poll(async () => parseMoney(await subtotal.textContent()), { timeout: 3_000 })
      .toBe(unitPrice * 3)
  })
})
