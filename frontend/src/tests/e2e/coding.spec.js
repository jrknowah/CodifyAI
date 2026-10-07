import { test, expect } from '@playwright/test'
import { USER, loginAs } from './helpers'

const SAMPLE_NOTE = `Patient is a 74-year-old male, POD #12 following right total hip arthroplasty.
Admitted to recuperative care for skilled nursing and PT. PMH: essential hypertension
controlled on lisinopril, type 2 diabetes mellitus HbA1c 7.1%, hyperlipidemia.
Currently ambulating 50 feet with rolling walker, pain 3/10, wound healing without
erythema or drainage. Continue DVT prophylaxis with enoxaparin.`

test.describe('Coding workflow', () => {
  test('dashboard loads with analyzer UI', async ({ page }) => {
    await loginAs(page, USER)
    await expect(page.getByRole('heading', { name: 'Code Analyzer' })).toBeVisible()
    await expect(page.getByTestId('note-input')).toBeVisible()
    await expect(page.getByTestId('facility-select')).toBeVisible()
    await expect(page.getByTestId('analyze-button')).toBeVisible()
  })

  test('analyze button is disabled when note is too short', async ({ page }) => {
    await loginAs(page, USER)
    await page.getByTestId('note-input').fill('Too short')
    await expect(page.getByTestId('analyze-button')).toBeDisabled()
  })

  test('sample note buttons populate textarea', async ({ page }) => {
    await loginAs(page, USER)
    await page.click('button:has-text("Hip Replacement")')
    const value = await page.getByTestId('note-input').inputValue()
    expect(value.length).toBeGreaterThan(30)
    await expect(page.getByTestId('analyze-button')).toBeEnabled()
  })

  test('analyze returns code results', async ({ page }) => {
    await loginAs(page, USER)
    await page.getByTestId('note-input').fill(SAMPLE_NOTE)
    await page.getByTestId('analyze-button').click()

    // Wait for results (AI call may take a few seconds)
    await expect(page.getByTestId('results-container')).toBeVisible({ timeout: 30_000 })
    const cards = page.locator('[data-testid="results-container"] > div')
    expect(await cards.count()).toBeGreaterThan(0)
  })

  test('character counter updates and warns near limit', async ({ page }) => {
    await loginAs(page, USER)
    const longNote = 'A'.repeat(9600)
    await page.getByTestId('note-input').fill(longNote)
    await expect(page.getByText(/9,600/)).toBeVisible()
  })

  test('history page shows completed encounter', async ({ page }) => {
    await loginAs(page, USER)

    // Run an analysis first
    await page.getByTestId('note-input').fill(SAMPLE_NOTE)
    await page.getByTestId('analyze-button').click()
    await expect(page.getByTestId('results-container')).toBeVisible({ timeout: 30_000 })

    // Navigate to history
    await page.click('a[href="/history"]')
    await expect(page.getByText('Encounter History')).toBeVisible()
    // At least one encounter should be listed
    const cards = page.locator('main [style*="border"]')
    expect(await cards.count()).toBeGreaterThan(0)
  })

  test('sidebar navigation works', async ({ page }) => {
    await loginAs(page, USER)
    await page.click('a[href="/history"]')
    await expect(page).toHaveURL(/\/history/)
    await page.click('a[href="/settings"]')
    await expect(page).toHaveURL(/\/settings/)
    await page.click('a[href="/dashboard"]')
    await expect(page).toHaveURL(/\/dashboard/)
  })
})
