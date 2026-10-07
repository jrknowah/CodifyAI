import { useState, useEffect } from 'react'
import QRCode from 'qrcode'
import { codingApi, authApi } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import Sidebar from '../components/layout/Sidebar'
import { Card, Alert, MonoBadge, Button, Input, Spinner } from '../components/ui'

// ─── History ─────────────────────────────────────────────────────────────────

export function History() {
  const [encounters, setEncounters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    codingApi.history()
      .then(res => setEncounters(res.data))
      .catch(() => setError('Could not load encounter history.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
        <div style={{ marginBottom: '1.75rem' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#e8f0eb', marginBottom: 4 }}>Encounter History</h1>
          <p style={{ color: '#6B9E8A', fontSize: 14 }}>All coding sessions. Clinical notes are never stored — only metadata and the codes assigned.</p>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        {loading && <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner size={32} /></div>}

        {!loading && encounters.length === 0 && !error && (
          <Card style={{ textAlign: 'center', padding: '3rem', color: '#3d5446' }}>
            <span style={{ fontSize: 40, display: 'block', marginBottom: 12 }}>📋</span>
            No encounters yet. Analyze a clinical note to get started.
          </Card>
        )}

        {encounters.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {encounters.map((e) => (
              <Card key={e.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1.5rem' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                    <MonoBadge>{e.top_code}</MonoBadge>
                    <span style={{ fontSize: 11, color: '#6B9E8A', textTransform: 'uppercase', letterSpacing: '1px' }}>{e.facility_type}</span>
                  </div>
                  <p style={{ fontSize: 11, fontFamily: 'monospace', color: '#3d5446' }}>
                    {e.id.toString().slice(0, 8)} · {new Date(e.created_at).toLocaleString()} · {e.note_length} chars
                  </p>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <p style={{ fontSize: 22, fontFamily: 'Georgia, serif', fontWeight: 700, color: '#2ECC71', lineHeight: 1 }}>{e.code_count}</p>
                  <p style={{ fontSize: 10, color: '#3d5446', textTransform: 'uppercase', letterSpacing: '1px' }}>codes</p>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

// ─── Settings ────────────────────────────────────────────────────────────────

export function Settings() {
  const { user } = useAuth()

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto', maxWidth: 640 }}>
        <div style={{ marginBottom: '1.75rem' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#e8f0eb', marginBottom: 4 }}>Settings</h1>
        </div>

        {user?.mfa_enrollment_required && (
          <div style={{ marginBottom: '1.5rem' }}>
            <Alert type="info">Your organization requires two-factor authentication. Set it up below to continue.</Alert>
          </div>
        )}

        {/* Account info */}
        <Card style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e8f0eb', marginBottom: '1rem' }}>Account</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
            {[
              ['Name', user?.full_name],
              ['Email', user?.email],
              ['Role', user?.role],
              ['Member since', user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'],
            ].map(([label, value]) => (
              <div key={label}>
                <p style={{ fontSize: 11, color: '#3d5446', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 2 }}>{label}</p>
                <p style={{ fontSize: 14, color: '#e8f0eb' }}>{value}</p>
              </div>
            ))}
          </div>
        </Card>

        <MfaSettings />
        {!user?.mfa_enrollment_required && <ChangePassword />}
      </main>
    </div>
  )
}

function MfaSettings() {
  const { user, refreshUser } = useAuth()
  const [setup, setSetup] = useState(null)   // { secret, qr }
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const run = async (fn) => {
    setError('')
    setSuccess('')
    setLoading(true)
    try { await fn() } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.')
    } finally { setLoading(false) }
  }

  const start = () => run(async () => {
    const res = await authApi.mfaSetup()
    const qr = await QRCode.toDataURL(res.data.otpauth_uri, { margin: 1, width: 200 })
    setSetup({ secret: res.data.secret, qr })
  })

  const enable = (e) => {
    e.preventDefault()
    run(async () => {
      await authApi.mfaEnable(code.trim())
      setSetup(null)
      setCode('')
      await refreshUser()
      setSuccess('Two-factor authentication is on.')
    })
  }

  const disable = (e) => {
    e.preventDefault()
    run(async () => {
      await authApi.mfaDisable(password, code.trim())
      setPassword('')
      setCode('')
      await refreshUser()
      setSuccess('Two-factor authentication is off.')
    })
  }

  return (
    <Card style={{ marginBottom: '1.5rem' }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e8f0eb', marginBottom: '0.5rem' }}>Two-factor authentication</h2>
      <p style={{ fontSize: 13, color: '#6B9E8A', marginBottom: '1rem' }}>
        {user?.mfa_enabled
          ? 'On — sign-in requires a code from your authenticator app.'
          : 'Off — add a code from an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password…) to every sign-in.'}
      </p>
      {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}
      {success && <div style={{ marginBottom: '1rem' }}><Alert type="success">{success}</Alert></div>}

      {!user?.mfa_enabled && !setup && (
        <Button onClick={start} disabled={loading} data-testid="mfa-setup-button">Set up two-factor authentication</Button>
      )}

      {!user?.mfa_enabled && setup && (
        <form onSubmit={enable}>
          <p style={{ fontSize: 13, color: '#e8f0eb', marginBottom: '0.75rem' }}>1. Scan this QR code with your authenticator app:</p>
          <img src={setup.qr} alt="MFA QR code" width={200} height={200} style={{ borderRadius: 8, marginBottom: '0.75rem' }} />
          <p style={{ fontSize: 12, color: '#6B9E8A', marginBottom: '1rem' }}>
            Can't scan? Enter this key: <code style={{ color: '#2ECC71', wordBreak: 'break-all' }}>{setup.secret}</code>
          </p>
          <Input label="2. Enter the 6-digit code it shows" value={code} onChange={e => setCode(e.target.value)}
            inputMode="numeric" autoComplete="one-time-code" maxLength={6} required data-testid="mfa-enable-code" />
          <Button type="submit" disabled={loading || code.trim().length !== 6}>Turn on</Button>
        </form>
      )}

      {user?.mfa_enabled && !user?.mfa_enrollment_required && (
        <form onSubmit={disable}>
          <Input label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          <Input label="Current 6-digit code" value={code} onChange={e => setCode(e.target.value)}
            inputMode="numeric" autoComplete="one-time-code" maxLength={6} required />
          <Button type="submit" variant="danger" disabled={loading}>Turn off</Button>
        </form>
      )}
    </Card>
  )
}

function ChangePassword() {
  const { startSession } = useAuth()
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (f) => (e) => setForm(prev => ({ ...prev, [f]: e.target.value }))

  const handlePasswordChange = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (form.new_password !== form.confirm) {
      setError('New passwords do not match.')
      return
    }
    setLoading(true)
    try {
      const res = await authApi.changePassword({ current_password: form.current_password, new_password: form.new_password })
      // Every other session was signed out; continue this one with the fresh token
      await startSession(res.data.access_token)
      setSuccess('Password updated. Other devices have been signed out.')
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : detail?.[0]?.msg || 'Password change failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e8f0eb', marginBottom: '1rem' }}>Change password</h2>
      {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}
      {success && <div style={{ marginBottom: '1rem' }}><Alert type="success">{success}</Alert></div>}
      <form onSubmit={handlePasswordChange}>
        <Input label="Current password" type="password" value={form.current_password} onChange={set('current_password')} autoComplete="current-password" required />
        <Input label="New password" type="password" value={form.new_password} onChange={set('new_password')} placeholder="Min. 12 chars, uppercase, number, special" autoComplete="new-password" required />
        <Input label="Confirm new password" type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" required />
        <Button type="submit" disabled={loading}>
          {loading ? 'Updating...' : 'Update password'}
        </Button>
      </form>
    </Card>
  )
}
