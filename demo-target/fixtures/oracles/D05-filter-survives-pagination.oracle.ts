import { expect, test } from '@playwright/test'

test('D05 category filter remains active on page 2', async ({ page }) => {
  const pagination = page.getByRole('navigation', { name: 'Pagination' })

  await test.step('setup: filter to Kitchen', async () => {
    await page.goto('/shop')
    await page.getByLabel('Category').selectOption('Kitchen')
    await expect(page.getByTestId('product-category').first()).toHaveText('Kitchen')
  })

  await test.step('setup: go to page 2', async () => {
    await pagination.getByRole('link', { name: 'Page 2' }).click()
    await expect(pagination.locator('[aria-current="page"]')).toHaveText('2')
  })

  await test.step('oracle: only Kitchen products and filter still selected', async () => {
    await expect(page.getByLabel('Category')).toHaveValue('Kitchen')
    const categories = await page.getByTestId('product-category').allTextContents()
    expect(categories.length).toBeGreaterThan(0)
    expect(new Set(categories)).toEqual(new Set(['Kitchen']))
  })
})
