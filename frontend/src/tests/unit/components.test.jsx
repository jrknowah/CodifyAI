import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// ── Mock auth context ──────────────────────────────────────────────────────────
const mockLogin = vi.fn()
const mockVerifyMfa = vi.fn()
const mockLogout = vi.fn()
const mockNavigate = vi.fn()
let authState = {}

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: null, loading: false, signedOutReason: null,
    login: mockLogin, verifyMfa: mockVerifyMfa, logout: mockLogout,
    ...authState,
  }),
  AuthProvider: ({ children }) => children,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

import Login from '../../pages/Login'
import ProtectedRoute from '../../components/layout/ProtectedRoute'

// ── Login component tests ─────────────────────────────────────────────────────

describe('Login page', () => {
  beforeEach(() => { vi.clearAllMocks(); authState = {} })

  const renderLogin = () =>
    render(<MemoryRouter><Login /></MemoryRouter>)

  const fillAndSubmit = async (email = 'test@test.com', password = 'TestPass123!') => {
    await userEvent.type(screen.getByTestId('email-input'), email)
    await userEvent.type(screen.getByTestId('password-input'), password)
    await userEvent.click(screen.getByTestId('login-button'))
  }

  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByTestId('email-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
    expect(screen.getByTestId('login-button')).toBeInTheDocument()
  })

  it('shows CodifyAI branding', () => {
    renderLogin()
    expect(screen.getAllByText(/Codify/i).length).toBeGreaterThan(0)
  })

  it('has no self-registration link', () => {
    renderLogin()
    expect(screen.queryByText(/^Register$/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Ask your administrator/i)).toBeInTheDocument()
  })

  it('calls login with email and password and goes to the dashboard', async () => {
    mockLogin.mockResolvedValueOnce({ user: { email: 'test@test.com' } })
    renderLogin()
    await fillAndSubmit()
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@test.com', 'TestPass123!')
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('sends users who must enroll in MFA to settings', async () => {
    mockLogin.mockResolvedValueOnce({ user: { email: 'a@b.c', mfa_enrollment_required: true } })
    renderLogin()
    await fillAndSubmit()
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/settings'))
  })

  it('asks for a code when MFA is required, then verifies it', async () => {
    mockLogin.mockResolvedValueOnce({ mfaRequired: true, mfaToken: 'mfa-token' })
    mockVerifyMfa.mockResolvedValueOnce({ user: { email: 'test@test.com' } })
    renderLogin()
    await fillAndSubmit()

    const codeInput = await screen.findByTestId('mfa-code-input')
    expect(screen.getByText(/Two-factor verification/i)).toBeInTheDocument()
    await userEvent.type(codeInput, '123456')
    await userEvent.click(screen.getByTestId('mfa-verify-button'))

    await waitFor(() => {
      expect(mockVerifyMfa).toHaveBeenCalledWith('mfa-token', '123456')
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('shows a generic error on failed login', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 401, data: { detail: 'Incorrect email or password.' } } })
    renderLogin()
    await fillAndSubmit('bad@test.com', 'WrongPass!')
    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument()
    })
  })

  it('shows a rate-limit message on 429', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 429 } })
    renderLogin()
    await fillAndSubmit()
    await waitFor(() => expect(screen.getByText(/Too many attempts/i)).toBeInTheDocument())
  })

  it('explains an idle sign-out', () => {
    authState = { signedOutReason: 'idle' }
    renderLogin()
    expect(screen.getByText(/inactivity/i)).toBeInTheDocument()
  })

  it('disables submit button while loading', async () => {
    mockLogin.mockImplementation(() => new Promise(() => {})) // never resolves
    renderLogin()
    await fillAndSubmit()
    expect(screen.getByTestId('login-button')).toBeDisabled()
  })
})

// ── Route guard ───────────────────────────────────────────────────────────────

describe('ProtectedRoute', () => {
  beforeEach(() => { authState = {} })

  const renderAt = (path, roles) => render(
    <MemoryRouter initialEntries={[path]}>
      <ProtectedRoute roles={roles}><p>secret page</p></ProtectedRoute>
    </MemoryRouter>
  )

  it('hides content from signed-out users', () => {
    renderAt('/dashboard')
    expect(screen.queryByText('secret page')).not.toBeInTheDocument()
  })

  it('hides admin pages from non-admins', () => {
    authState = { user: { role: 'coder' } }
    renderAt('/admin', ['admin'])
    expect(screen.queryByText('secret page')).not.toBeInTheDocument()
  })

  it('shows admin pages to admins', () => {
    authState = { user: { role: 'admin' } }
    renderAt('/admin', ['admin'])
    expect(screen.getByText('secret page')).toBeInTheDocument()
  })

  it('holds users who must enroll in MFA on the settings page', () => {
    authState = { user: { role: 'coder', mfa_enrollment_required: true } }
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<ProtectedRoute><p>secret page</p></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><p>settings page</p></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.queryByText('secret page')).not.toBeInTheDocument()
    expect(screen.getByText('settings page')).toBeInTheDocument()
  })
})

// ── UI component tests ────────────────────────────────────────────────────────
import { Alert, Button, MonoBadge } from '../../components/ui'

describe('UI components', () => {
  it('Alert renders error correctly', () => {
    render(<Alert type="error">Something went wrong</Alert>)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('Alert renders success correctly', () => {
    render(<Alert type="success">Saved!</Alert>)
    expect(screen.getByText('Saved!')).toBeInTheDocument()
  })

  it('Button is disabled when disabled prop passed', () => {
    render(<Button disabled>Click me</Button>)
    expect(screen.getByText('Click me')).toBeDisabled()
  })

  it('MonoBadge renders code', () => {
    render(<MonoBadge>Z87.891</MonoBadge>)
    expect(screen.getByText('Z87.891')).toBeInTheDocument()
  })
})
