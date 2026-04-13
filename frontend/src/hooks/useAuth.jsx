import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authApi, tokenStore } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On mount: try to restore session via refresh token in sessionStorage
  useEffect(() => {
    const refresh = sessionStorage.getItem('refresh_token')
    if (!refresh) { setLoading(false); return }

    authApi.refresh(refresh)
      .then(res => {
        tokenStore.set(res.data.access_token)
        sessionStorage.setItem('refresh_token', res.data.refresh_token)
        return authApi.me()
      })
      .then(res => setUser(res.data))
      .catch(() => {
        tokenStore.clear()
        sessionStorage.clear()
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await authApi.login(email, password)
    tokenStore.set(res.data.access_token)
    // Refresh token goes to sessionStorage (cleared when tab closes)
    sessionStorage.setItem('refresh_token', res.data.refresh_token)
    const me = await authApi.me()
    setUser(me.data)
    return me.data
  }, [])

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* ignore */ }
    tokenStore.clear()
    sessionStorage.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
