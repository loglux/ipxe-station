import { expect, test } from '@playwright/test'

test('builder page renders and preview refresh works without runtime errors', async ({ page }) => {
  const runtimeErrors = []

  page.on('pageerror', (error) => {
    runtimeErrors.push(error.message)
  })

  page.on('console', (msg) => {
    if (msg.type() === 'error') runtimeErrors.push(msg.text())
  })

  await page.goto('/#builder', { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: /Welcome to iPXE Menu Builder/i })).toBeVisible()
  await expect(page.getByRole('button', { name: /Save Menu/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)

  await page.getByText(/iPXE Script Preview/i).click()
  await expect(page.getByRole('button', { name: /Refresh/i })).toBeVisible()

  await page.getByRole('button', { name: /Refresh/i }).click()
  await expect(page.locator('.code-preview')).toContainText('#!ipxe')

  const entriesCountText = page.locator('.footer-right span').first()
  const beforeText = await entriesCountText.textContent()
  const beforeEntries = Number((beforeText || '').replace(/\D/g, ''))

  const entryButtons = page.locator('.tree-select-btn')
  if (await entryButtons.count()) {
    await entryButtons.first().click()
    await expect(page.getByRole('button', { name: /Duplicate/i })).toBeVisible()
    await page.getByRole('button', { name: /Duplicate/i }).click()

    await expect.poll(async () => {
      const text = await entriesCountText.textContent()
      return Number((text || '').replace(/\D/g, ''))
    }).toBe(beforeEntries + 1)

    await page.getByRole('button', { name: /Disable all/i }).click()
    await expect(page.locator('.badge-disabled').first()).toBeVisible()

    await page.getByRole('button', { name: /Enable all/i }).click()
    await expect(page.locator('.badge-disabled')).toHaveCount(0)
  } else {
    await expect(page.getByRole('button', { name: /Enable all/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /Disable all/i })).toBeVisible()
  }

  expect(runtimeErrors).toEqual([])
})
