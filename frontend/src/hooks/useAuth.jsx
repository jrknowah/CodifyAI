import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { authApi, tokenStore, refreshSession, setSessionExpiredHandler } from '../services/api'

const AuthContext = createContext(null)

// HIPAA §164.312(a)(2)(iii) automatic logoff: sign out after this much inactivity.
const IDLE_TIMEOUT_MS = (Number(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES) || 15) * 60 * 1000
const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'scroll', 'touchstart']

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // Why the user was signed out ('idle' | 'expired'), shown on the login page
  const [signedOutReason, setSignedOutReason] = useState(null)
  const idleTimer = useRef(null)

  const endSession = useCallback((reason) => {
    tokenStore.clear()
    setUser(null)
    setSignedOutReason(reason || null)
  }, [])

  const logout = useCallback(async (reason) => {
    try { await authApi.logout() } catch { /* ignore */ }
    endSession(typeof reason === 'string' ? reason : null)
  }, [endSession])

  // The API layer calls this when the refresh cookie is rejected
  useEffect(() => {
    setSessionExpiredHandler((reason) => endSession(reason))
  }, [endSession])

  // On mount: restore the session from the httpOnly refresh cookie, if any
  useEffect(() => {
    // No cookie / expired session just means "not signed in". Don't clear the token
    // here: the user may have logged in while this request was in flight.
    refreshSession()
      .then(() => authApi.me())
      .then(res => setUser(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Automatic logoff after inactivity
  useEffect(() => {
    if (!user) return
    const reset = () => {
      clearTimeout(idleTimer.current)
      idleTimer.current = setTimeout(() => logout('idle'), IDLE_TIMEOUT_MS)
    }
    reset()
    ACTIVITY_EVENTS.forEach(e => window.addEventListener(e, reset, { passive: true }))
    return () => {
      clearTimeout(idleTimer.current)
      ACTIVITY_EVENTS.forEach(e => window.removeEventListener(e, reset))
    }
  }, [user, logout])

  const startSession = useCallback(async (accessToken) => {
    tokenStore.set(accessToken)
    const me = await authApi.me()
    setSignedOutReason(null)
    setUser(me.data)
    return me.data
  }, [])

  /** Password step. Resolves to { mfaRequired: true, mfaToken } or { user }. */
  const login = useCallback(async (email, password) => {
    const res = await authApi.login(email, password)
    if (res.data.mfa_required) return { mfaRequired: true, mfaToken: res.data.mfa_token }
    return { user: await startSession(res.data.access_token) }
  }, [startSession])

  /** Second step for MFA users. */
  const verifyMfa = useCallback(async (mfaToken, code) => {
    const res = await authApi.verifyMfa(mfaToken, code)
    return { user: await startSession(res.data.access_token) }
  }, [startSession])

  const refreshUser = useCallback(async () => {
    const me = await authApi.me()
    setUser(me.data)
    return me.data
  }, [])

  return (
    <AuthContext.Provider value={{
      user, loading, signedOutReason, login, verifyMfa, logout, refreshUser, startSession,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

// The hook lives beside its provider on purpose; fast refresh falls back to a full reload here.
// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
