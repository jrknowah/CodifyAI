import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

// ── Mock auth context ──────────────────────────────────────────────────────────
const mockLogin = vi.fn()
const mockLogout = vi.fn()

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ user: null, login: mockLogin, logout: mockLogout, loading: false }),
  AuthProvider: ({ children }) => children,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => vi.fn() }
})

import Login from '../pages/Login'

// ── Login component tests ─────────────────────────────────────────────────────

describe('Login page', () => {
  beforeEach(() => { vi.clearAllMocks() })

  const renderLogin = () =>
    render(<MemoryRouter><Login /></MemoryRouter>)

  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByTestId('email-input')).toBeInTheDocument()
    expect(screen.getByTestId('password-input')).toBeInTheDocument()
    expect(screen.getByTestId('login-button')).toBeInTheDocument()
  })

  it('shows CodifyAI branding', () => {
    renderLogin()
    expect(screen.getByText(/CodifyAI/i)).toBeInTheDocument()
  })

  it('calls login with email and password on submit', async () => {
    mockLogin.mockResolvedValueOnce({ email: 'test@test.com' })
    renderLogin()
    await userEvent.type(screen.getByTestId('email-input'), 'test@test.com')
    await userEvent.type(screen.getByTestId('password-input'), 'TestPass123!')
    await userEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@test.com', 'TestPass123!')
    })
  })

  it('shows error message on failed login', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 401, data: { detail: 'Incorrect email or password.' } } })
    renderLogin()
    await userEvent.type(screen.getByTestId('email-input'), 'bad@test.com')
    await userEvent.type(screen.getByTestId('password-input'), 'WrongPass!')
    await userEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument()
    })
  })

  it('shows locked message on 423 response', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 423, data: { detail: 'Account temporarily locked.' } } })
    renderLogin()
    await userEvent.type(screen.getByTestId('email-input'), 'locked@test.com')
    await userEvent.type(screen.getByTestId('password-input'), 'AnyPass123!')
    await userEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(screen.getByText(/locked/i)).toBeInTheDocument()
    })
  })

  it('disables submit button while loading', async () => {
    mockLogin.mockImplementation(() => new Promise(() => {})) // never resolves
    renderLogin()
    await userEvent.type(screen.getByTestId('email-input'), 'test@test.com')
    await userEvent.type(screen.getByTestId('password-input'), 'TestPass123!')
    await userEvent.click(screen.getByTestId('login-button'))
    expect(screen.getByTestId('login-button')).toBeDisabled()
  })
})

// ── UI component tests ────────────────────────────────────────────────────────
import { Alert, Button, MonoBadge } from '../components/ui'

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
