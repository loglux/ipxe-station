import { expect, test } from '@playwright/test'

test('dhcp page renders and mode switch works without runtime errors', async ({ page }) => {
  const runtimeErrors = []

  page.on('pageerror', (error) => {
    runtimeErrors.push(error.message)
  })

  page.on('console', (msg) => {
    if (msg.type() === 'error') runtimeErrors.push(msg.text())
  })

  await page.goto('/#dhcp', { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: /DHCP Configuration Helper/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)

  await page.getByRole('button', { name: /Router DHCP config/i }).click()
  await expect(page.getByRole('heading', { name: /Configure your router's DHCP server/i })).toBeVisible()

  await page.getByRole('button', { name: /Proxy DHCP/i }).click()
  await expect(page.getByRole('heading', { name: /Proxy DHCP Server/i })).toBeVisible()

  expect(runtimeErrors).toEqual([])
})
