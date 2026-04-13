import { test, expect } from '@playwright/test'

const TEST_USER = {
  email: 'e2e@codifyai.com',
  password: 'E2eTestPass123!',
  name: 'E2E Tester',
}

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

  test('register → login → dashboard flow', async ({ page }) => {
    // Register
    await page.click('text=Register')
    await page.getByTestId('name-input').fill(TEST_USER.name)
    await page.getByTestId('email-input').fill(TEST_USER.email)
    await page.getByTestId('password-input').fill(TEST_USER.password)
    await page.click('button[type=submit]')
    await expect(page).toHaveURL(/\/login/)

    // Login
    await page.getByTestId('email-input').fill(TEST_USER.email)
    await page.getByTestId('password-input').fill(TEST_USER.password)
    await page.getByTestId('login-button').click()
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByText('Code Analyzer')).toBeVisible()
  })

  test('logout clears session and redirects to login', async ({ page }) => {
    // Login first
    await page.getByTestId('email-input').fill(TEST_USER.email)
    await page.getByTestId('password-input').fill(TEST_USER.password)
    await page.getByTestId('login-button').click()
    await expect(page).toHaveURL(/\/dashboard/)

    // Logout
    await page.click('button:has-text("Sign out")')
    await expect(page).toHaveURL(/\/login/)

    // Confirm protected route is blocked
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })
})
