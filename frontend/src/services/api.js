import axios from 'axios'

// ── Token stored in memory (not localStorage) to prevent XSS theft ────────────
let _accessToken = null
let _refreshPromise = null

export const tokenStore = {
  set: (token) => { _accessToken = token },
  get: () => _accessToken,
  clear: () => { _accessToken = null },
}

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: false,
})

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config

    if (err.response?.status === 401 && !original._retry) {
      original._retry = true

      // Only one refresh call at a time
      if (!_refreshPromise) {
        const stored = sessionStorage.getItem('refresh_token')
        if (!stored) {
          tokenStore.clear()
          sessionStorage.clear()
          window.location.href = '/login'
          return Promise.reject(err)
        }

        _refreshPromise = api.post('/auth/refresh', { refresh_token: stored })
          .then(res => {
            tokenStore.set(res.data.access_token)
            sessionStorage.setItem('refresh_token', res.data.refresh_token)
          })
          .catch(() => {
            tokenStore.clear()
            sessionStorage.clear()
            window.location.href = '/login'
          })
          .finally(() => { _refreshPromise = null })
      }

      await _refreshPromise
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
  refresh: (refresh_token) => api.post('/auth/refresh', { refresh_token }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  register: (data) => api.post('/auth/register', data),
  changePassword: (data) => api.post('/auth/change-password', data),
}

export const codingApi = {
  analyze: (clinicalNote, facilityType = 'post-acute') =>
    api.post('/coding/analyze', { clinical_note: clinicalNote, facility_type: facilityType }),
  history: (limit = 20, offset = 0) =>
    api.get(`/coding/history?limit=${limit}&offset=${offset}`),
}

export default api
