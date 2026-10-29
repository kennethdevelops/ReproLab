import { expect, type Page } from '@playwright/test'

export function parseMoney(text: string | null): number {
  const match = (text ?? '').replace(/[,−-]/g, '').match(/\$([0-9]+(?:\.[0-9]{2})?)/)
  if (!match) throw new Error(`no money value in ${JSON.stringify(text)}`)
  return Math.round(Number(match[1]) * 100)
}

/** Precondition shared by cart/checkout oracles: one known product in the cart. */
export async function addProductToCart(page: Page, productName: string): Promise<void> {
  await page.goto('/shop')
  await page.getByRole('button', { name: `Add ${productName} to cart` }).click()
  await expect(page.getByRole('status').filter({ hasText: `Added ${productName}` })).toBeVisible()
}
