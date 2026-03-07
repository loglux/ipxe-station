import { expect, test } from '@playwright/test'

test('boot files page renders without runtime errors', async ({ page }) => {
  const runtimeErrors = []

  page.on('pageerror', (error) => {
    runtimeErrors.push(error.message)
  })

  page.on('console', (msg) => {
    if (msg.type() === 'error') runtimeErrors.push(msg.text())
  })

  await page.goto('/#boot', { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: /autoexec\.ipxe/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: /preseed\.cfg/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)

  await expect(page.getByRole('button', { name: /^Apply$/ }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /Save/i }).first()).toBeVisible()

  expect(runtimeErrors).toEqual([])
})
