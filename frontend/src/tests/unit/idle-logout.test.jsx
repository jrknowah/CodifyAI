import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

const logoutApi = vi.fn(() => Promise.resolve())
vi.mock('../../services/api', () => ({
  authApi: {
    me: () => Promise.resolve({ data: { email: 'a@b.c', role: 'coder' } }),
    logout: (...args) => logoutApi(...args),
  },
  tokenStore: { set: vi.fn(), get: vi.fn(), clear: vi.fn() },
  refreshSession: () => Promise.resolve({ access_token: 't' }),
  setSessionExpiredHandler: vi.fn(),
}))

import { AuthProvider, useAuth } from '../../hooks/useAuth'

function Probe() {
  const { user, signedOutReason } = useAuth()
  return <p>{user ? `in:${user.email}` : `out:${signedOutReason}`}</p>
}

describe('automatic logoff', () => {
  it('signs the user out after 15 minutes without activity', async () => {
    vi.useFakeTimers()
    render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(screen.getByText('in:a@b.c')).toBeInTheDocument()

    // Activity at 14 minutes pushes the deadline out
    await act(async () => { await vi.advanceTimersByTimeAsync(14 * 60 * 1000) })
    await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown')) })
    await act(async () => { await vi.advanceTimersByTimeAsync(14 * 60 * 1000) })
    expect(screen.getByText('in:a@b.c')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 60 * 1000) })
    expect(logoutApi).toHaveBeenCalled()
    expect(screen.getByText('out:idle')).toBeInTheDocument()
    vi.useRealTimers()
  })
})
