import { expect, test } from '@playwright/test'

test('monitoring page downloads logs via backend endpoint without runtime errors', async ({ page }) => {
  const runtimeErrors = []
  const insecureBlobWarnings = []

  page.on('pageerror', (error) => {
    runtimeErrors.push(error.message)
  })

  page.on('console', (msg) => {
    const text = msg.text()
    if (msg.type() === 'error') runtimeErrors.push(text)
    if (text.includes('blob:http://') && text.includes('insecure connection')) {
      insecureBlobWarnings.push(text)
    }
  })

  await page.goto('/#monitoring', { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: /System Logs/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)

  await page.locator('.logs-controls select').nth(0).selectOption('boot')
  await page.locator('.logs-controls select').nth(1).selectOption('warning')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /Download/i }).click()
  const download = await downloadPromise

  expect(download.url()).toContain('/api/monitoring/logs/download')
  expect(download.url()).toContain('type=boot')
  expect(download.url()).toContain('level=warning')
  expect(download.suggestedFilename()).toMatch(/^ipxe-logs-\d{8}-\d{6}\.txt$/)
  expect(runtimeErrors).toEqual([])
  expect(insecureBlobWarnings).toEqual([])
})
