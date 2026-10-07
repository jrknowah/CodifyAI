/* global process */
import { expect } from '@playwright/test'

// Self-registration is disabled, so e2e runs against a pre-provisioned coder
// account (without MFA). Create it once, e.g.:
//   python -m app.cli create-admin ...   then add the coder on /admin
// and export E2E_EMAIL / E2E_PASSWORD before `npx playwright test`.
export const USER = {
  email: process.env.E2E_EMAIL || 'coder@codifyai.com',
  password: process.env.E2E_PASSWORD || 'CoderPass123!',
}

export async function loginAs(page, user = USER) {
  await page.goto('/login')
  await page.getByTestId('email-input').fill(user.email)
  await page.getByTestId('password-input').fill(user.password)
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL(/\/dashboard/)
}
