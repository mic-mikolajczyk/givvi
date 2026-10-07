import { expect, test } from '@playwright/test'

test('displays real readiness in English and Polish without overflow', async ({ page }) => {
  await page.goto('/status')

  await expect(page.getByRole('heading', { name: 'Service status' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Connected')
  await page.getByRole('combobox', { name: 'Language' }).selectOption('pl')
  await expect(page.getByRole('status')).toHaveText('Połączono')
  await expect(page.locator('html')).toHaveAttribute('lang', 'pl')
  await expect(page.getByRole('heading', { name: 'Stan usługi' })).toBeVisible()
  const fitsViewport = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(fitsViewport).toBe(true)
  await page.screenshot({ path: test.info().outputPath('status.png'), fullPage: true })
})

test('recovers from an unavailable response', async ({ page }) => {
  await page.route('**/api/health/ready', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'unavailable' }),
  }))
  await page.goto('/status')
  await expect(page.getByRole('status')).toHaveText('Unavailable')

  await page.unroute('**/api/health/ready')
  await page.getByRole('button', { name: 'Check again' }).click()

  await expect(page.getByRole('status')).toHaveText('Connected')
})
