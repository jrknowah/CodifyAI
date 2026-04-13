import { useState, useEffect } from 'react'
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
          <p style={{ color: '#6B9E8A', fontSize: 14 }}>All coding sessions. Clinical notes are never stored — only metadata and results.</p>
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
      await authApi.changePassword({ current_password: form.current_password, new_password: form.new_password })
      setSuccess('Password updated successfully.')
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      setError(err.response?.data?.detail || 'Password change failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto', maxWidth: 640 }}>
        <div style={{ marginBottom: '1.75rem' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#e8f0eb', marginBottom: 4 }}>Settings</h1>
        </div>

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

        {/* Change password */}
        <Card>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e8f0eb', marginBottom: '1rem' }}>Change password</h2>
          {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}
          {success && <div style={{ marginBottom: '1rem' }}><Alert type="success">{success}</Alert></div>}
          <form onSubmit={handlePasswordChange}>
            <Input label="Current password" type="password" value={form.current_password} onChange={set('current_password')} required />
            <Input label="New password" type="password" value={form.new_password} onChange={set('new_password')} placeholder="Min. 12 chars, uppercase, number, special" required />
            <Input label="Confirm new password" type="password" value={form.confirm} onChange={set('confirm')} required />
            <Button type="submit" disabled={loading}>
              {loading ? 'Updating...' : 'Update password'}
            </Button>
          </form>
        </Card>
      </main>
    </div>
  )
}
