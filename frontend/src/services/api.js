import axios from 'axios'

// ── Token handling ────────────────────────────────────────────────────────────
// Access token: in memory only (not localStorage/sessionStorage) to limit XSS theft.
// Refresh token: an httpOnly, SameSite=Strict cookie set by the server — JavaScript
// can't read it at all. The page only ever asks the server to rotate it.
let _accessToken = null
let _refreshPromise = null
let _onSessionExpired = () => { window.location.href = '/login' }

export const tokenStore = {
  set: (token) => { _accessToken = token },
  get: () => _accessToken,
  clear: () => { _accessToken = null },
}

export const setSessionExpiredHandler = (fn) => { _onSessionExpired = fn }

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
})

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Endpoints whose 401 means "bad credentials", not "access token expired"
const NO_REFRESH = ['/auth/token', '/auth/refresh', '/auth/mfa/verify', '/auth/logout']

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

/**
 * Rotate the refresh cookie and store the new access token. Only one refresh runs
 * at a time in this tab. With `retry`, a 401 is retried once: another tab may have
 * rotated the shared cookie a moment before us. (Not used for the initial session
 * restore, where a 401 just means "not signed in".)
 */
export function refreshSession({ retry = false } = {}) {
  if (!_refreshPromise) {
    const attempt = () => api.post('/auth/refresh')
    _refreshPromise = attempt()
      .catch(err => {
        if (!retry || err.response?.status !== 401) throw err
        return sleep(400).then(attempt)
      })
      .then(res => { tokenStore.set(res.data.access_token); return res.data })
      .finally(() => { _refreshPromise = null })
  }
  return _refreshPromise
}

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const skip = NO_REFRESH.some(path => original?.url?.startsWith(path))

    if (err.response?.status === 401 && !original._retry && !skip) {
      original._retry = true
      try {
        await refreshSession({ retry: true })
      } catch {
        tokenStore.clear()
        _onSessionExpired('expired')
        return Promise.reject(err)
      }
      return api(original)
    }

    return Promise.reject(err)
  }
)

// ── API methods ───────────────────────────────────────────────────────────────

export const authApi = {
  login: (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    return api.post('/auth/token', form)
  },
  verifyMfa: (mfaToken, code) => api.post('/auth/mfa/verify', { mfa_token: mfaToken, code }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
  mfaSetup: () => api.post('/auth/mfa/setup'),
  mfaEnable: (code) => api.post('/auth/mfa/enable', { code }),
  mfaDisable: (password, code) => api.post('/auth/mfa/disable', { password, code }),
}

export const codingApi = {
  analyze: (clinicalNote, facilityType = 'post-acute') =>
    api.post('/coding/analyze', { clinical_note: clinicalNote, facility_type: facilityType }),
  history: (limit = 20, offset = 0) =>
    api.get('/coding/history', { params: { limit, offset } }),
}

export const adminApi = {
  listUsers: () => api.get('/admin/users'),
  createUser: (data) => api.post('/admin/users', data),
  updateUser: (id, data) => api.patch(`/admin/users/${id}`, data),
  unlockUser: (id) => api.post(`/admin/users/${id}/unlock`),
  resetMfa: (id) => api.post(`/admin/users/${id}/reset-mfa`),
  revokeSessions: (id) => api.post(`/admin/users/${id}/revoke-sessions`),
  auditLogs: (params = {}) => api.get('/admin/audit-logs', { params }),
}

export default api
