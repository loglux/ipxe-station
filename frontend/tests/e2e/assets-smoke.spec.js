import { expect, test } from '@playwright/test'

test('assets page loads without ErrorBoundary crash', async ({ page }) => {
  const boundaryErrors = []

  page.on('console', (msg) => {
    if (msg.type() !== 'error') return
    const text = msg.text()
    if (text.includes('[ErrorBoundary]') || text.includes('ReferenceError')) {
      boundaryErrors.push(text)
    }
  })

  await page.goto('/#assets', { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: 'Asset Manager' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)
  expect(boundaryErrors).toEqual([])
})

