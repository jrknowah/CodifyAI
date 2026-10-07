import { test, expect } from '@playwright/test'
import { loginAs } from './helpers'

test.describe('Authentication flows', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
  })

  test('login page renders correctly', async ({ page }) => {
    await expect(page.getByText('CodifyAI')).toBeVisible()
    await expect(page.getByTestId('email-input')).toBeVisible()
    await expect(page.getByTestId('password-input')).toBeVisible()
    await expect(page.getByTestId('login-button')).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.getByTestId('email-input').fill('wrong@test.com')
    await page.getByTestId('password-input').fill('WrongPassword123!')
    await page.getByTestId('login-button').click()
    await expect(page.getByText(/Invalid email or password/i)).toBeVisible()
  })

  test('redirects unauthenticated user to login', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })

  test('has no public registration', async ({ page }) => {
    await expect(page.getByText(/^Register$/)).toHaveCount(0)
    await page.goto('/register')
    await expect(page).toHaveURL(/\/login/)
  })

  test('login → dashboard flow', async ({ page }) => {
    await loginAs(page)
    await expect(page.getByRole('heading', { name: 'Code Analyzer' })).toBeVisible()
  })

  test('session survives a reload (httpOnly refresh cookie)', async ({ page }) => {
    await loginAs(page)
    await page.reload()
    await expect(page).toHaveURL(/\/dashboard/)
  })

  test('logout clears session and redirects to login', async ({ page }) => {
    await loginAs(page)

    // Logout
    await page.click('button:has-text("Sign out")')
    await expect(page).toHaveURL(/\/login/)

    // Confirm protected route is blocked
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })
})
