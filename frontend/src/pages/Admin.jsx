import { useState, useEffect, useCallback } from 'react'
import { adminApi } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import Sidebar from '../components/layout/Sidebar'
import { Card, Alert, Button, Input, Spinner, MonoBadge } from '../components/ui'

const ROLES = ['coder', 'viewer', 'admin']
const AUDIT_ACTIONS = [
  'login', 'login_failed', 'account_locked', 'logout', 'analyze', 'view_history',
  'user_created', 'user_updated', 'user_unlocked', 'password_changed',
  'mfa_enabled', 'mfa_disabled', 'mfa_reset', 'refresh_token_reuse', 'view_audit_log', 'export',
]

const th = { textAlign: 'left', fontSize: 11, color: '#3d5446', textTransform: 'uppercase', letterSpacing: '1px', padding: '8px 10px', borderBottom: '1px solid #1f2f26' }
const td = { fontSize: 13, color: '#e8f0eb', padding: '10px', borderBottom: '1px solid #1f2f26', verticalAlign: 'top' }
const select = { background: 'rgba(255,255,255,0.04)', border: '1px solid #1f2f26', borderRadius: 8, color: '#e8f0eb', fontSize: 13, padding: '8px 10px', fontFamily: 'inherit' }
const smallBtn = { padding: '6px 10px', fontSize: 12 }

const errorText = (err, fallback) => {
  const detail = err.response?.data?.detail
  return typeof detail === 'string' ? detail : detail?.[0]?.msg || fallback
}

export default function Admin() {
  const [tab, setTab] = useState('users')
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto' }}>
        <div style={{ marginBottom: '1.25rem' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#e8f0eb', marginBottom: 4 }}>Administration</h1>
          <p style={{ color: '#6B9E8A', fontSize: 14 }}>Manage user accounts and review the HIPAA audit trail.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: '1.25rem' }}>
          {[['users', 'Users'], ['audit', 'Audit log']].map(([key, label]) => (
            <Button key={key} variant={tab === key ? 'primary' : 'secondary'} style={smallBtn} onClick={() => setTab(key)}>{label}</Button>
          ))}
        </div>
        {tab === 'users' ? <Users /> : <AuditLog />}
      </main>
    </div>
  )
}

// ─── Users ───────────────────────────────────────────────────────────────────

function Users() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(() => {
    adminApi.listUsers()
      .then(res => setUsers(res.data))
      .catch(() => setError('Could not load users.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const act = async (fn, message) => {
    setError('')
    setNotice('')
    try {
      await fn()
      setNotice(message)
      load()
    } catch (err) {
      setError(errorText(err, 'Action failed.'))
    }
  }

  const isLocked = (u) => u.locked_until && new Date(u.locked_until) > new Date()

  return (
    <>
      <CreateUser onCreated={(u) => { setNotice(`Created ${u.email}.`); load() }} />

      {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}
      {notice && <div style={{ marginBottom: '1rem' }}><Alert type="success">{notice}</Alert></div>}

      <Card style={{ padding: '0.5rem', overflowX: 'auto' }}>
        {loading ? <div style={{ padding: '2rem', textAlign: 'center' }}><Spinner size={28} /></div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>{['User', 'Role', 'Status', 'MFA', 'Last login', 'Actions'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {users.map(u => {
                const self = u.id === me?.id
                return (
                  <tr key={u.id} data-testid="admin-user-row">
                    <td style={td}>
                      <div style={{ fontWeight: 600 }}>{u.full_name}</div>
                      <div style={{ fontSize: 12, color: '#6B9E8A' }}>{u.email}</div>
                    </td>
                    <td style={td}>
                      <select
                        style={select}
                        value={u.role}
                        disabled={self}
                        onChange={e => act(() => adminApi.updateUser(u.id, { role: e.target.value }), `Role updated for ${u.email}. Their sessions were signed out.`)}
                        aria-label={`Role for ${u.email}`}
                      >
                        {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td style={td}>
                      {!u.is_active ? <MonoBadge color="#e74c3c" bg="rgba(231,76,60,0.1)">disabled</MonoBadge>
                        : isLocked(u) ? <MonoBadge color="#f39c12" bg="rgba(243,156,18,0.1)">locked</MonoBadge>
                        : <MonoBadge>active</MonoBadge>}
                    </td>
                    <td style={td}>{u.mfa_enabled ? 'On' : <span style={{ color: '#6B9E8A' }}>Off</span>}</td>
                    <td style={{ ...td, fontSize: 12, color: '#6B9E8A' }}>{u.last_login ? new Date(u.last_login).toLocaleString() : '—'}</td>
                    <td style={td}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {isLocked(u) && (
                          <Button variant="secondary" style={smallBtn} onClick={() => act(() => adminApi.unlockUser(u.id), `Unlocked ${u.email}.`)}>Unlock</Button>
                        )}
                        {u.mfa_enabled && !self && (
                          <Button variant="secondary" style={smallBtn} onClick={() => {
                            if (window.confirm(`Reset MFA for ${u.email}? They will have to enroll again.`)) {
                              act(() => adminApi.resetMfa(u.id), `MFA reset for ${u.email}.`)
                            }
                          }}>Reset MFA</Button>
                        )}
                        {!self && (
                          <Button variant="secondary" style={smallBtn} onClick={() => act(() => adminApi.revokeSessions(u.id), `Signed out all sessions for ${u.email}.`)}>Sign out</Button>
                        )}
                        {!self && (
                          u.is_active
                            ? <Button variant="danger" style={smallBtn} onClick={() => {
                                if (window.confirm(`Disable ${u.email}? They will be signed out immediately.`)) {
                                  act(() => adminApi.updateUser(u.id, { is_active: false }), `Disabled ${u.email}.`)
                                }
                              }}>Disable</Button>
                            : <Button variant="secondary" style={smallBtn} onClick={() => act(() => adminApi.updateUser(u.id, { is_active: true }), `Re-enabled ${u.email}.`)}>Enable</Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}

function CreateUser({ onCreated }) {
  const empty = { full_name: '', email: '', password: '', role: 'coder' }
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(empty)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const set = (f) => (e) => setForm(prev => ({ ...prev, [f]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await adminApi.createUser({ ...form, email: form.email.trim().toLowerCase() })
      setForm(empty)
      setOpen(false)
      onCreated(res.data)
    } catch (err) {
      setError(errorText(err, 'Could not create user.'))
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return <Button style={{ ...smallBtn, marginBottom: '1rem' }} onClick={() => setOpen(true)} data-testid="admin-new-user">+ New user</Button>
  }

  return (
    <Card style={{ marginBottom: '1.25rem', maxWidth: 560 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e8f0eb', marginBottom: '1rem' }}>New user</h2>
      {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}
      <form onSubmit={submit}>
        <Input label="Full name" value={form.full_name} onChange={set('full_name')} required data-testid="admin-name" />
        <Input label="Email" type="email" value={form.email} onChange={set('email')} required autoComplete="off" data-testid="admin-email" />
        <Input label="Temporary password" type="password" value={form.password} onChange={set('password')}
          placeholder="Min. 12 chars, uppercase, number, special" required autoComplete="new-password" data-testid="admin-password" />
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: 12, color: '#6B9E8A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '1px' }}>Role</label>
          <select style={select} value={form.role} onChange={set('role')} data-testid="admin-role">
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <p style={{ fontSize: 12, color: '#6B9E8A', marginBottom: '1rem' }}>
          Share the temporary password securely and ask the user to change it in Settings after first sign-in.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button type="submit" disabled={loading} style={smallBtn}>{loading ? 'Creating...' : 'Create user'}</Button>
          <Button type="button" variant="secondary" style={smallBtn} onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </form>
    </Card>
  )
}

// ─── Audit log ───────────────────────────────────────────────────────────────

const PAGE = 50

function AuditLog() {
  const [logs, setLogs] = useState([])
  const [users, setUsers] = useState({})
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    adminApi.listUsers()
      .then(res => setUsers(Object.fromEntries(res.data.map(u => [u.id, u.email]))))
      .catch(() => {})
  }, [])

  useEffect(() => {
    adminApi.auditLogs({ limit: PAGE, offset, ...(action ? { action } : {}) })
      .then(res => setLogs(res.data))
      .catch(() => setError('Could not load the audit log.'))
      .finally(() => setLoading(false))
  }, [action, offset])

  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: '1rem' }}>
        <select style={select} value={action} onChange={e => { setLoading(true); setOffset(0); setAction(e.target.value) }} aria-label="Filter by action">
          <option value="">All actions</option>
          {AUDIT_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span style={{ fontSize: 12, color: '#3d5446' }}>Entries are append-only and can't be edited or deleted.</span>
      </div>

      {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}

      <Card style={{ padding: '0.5rem', overflowX: 'auto' }}>
        {loading ? <div style={{ padding: '2rem', textAlign: 'center' }}><Spinner size={28} /></div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>{['Time', 'User', 'Action', 'Result', 'IP', 'Detail'].map(h => <th key={h} style={th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {logs.length === 0 && <tr><td style={{ ...td, color: '#3d5446' }} colSpan={6}>No entries.</td></tr>}
              {logs.map(l => (
                <tr key={l.id}>
                  <td style={{ ...td, fontSize: 12, whiteSpace: 'nowrap' }}>{new Date(l.created_at).toLocaleString()}</td>
                  <td style={{ ...td, fontSize: 12 }}>{l.user_id ? (users[l.user_id] || l.user_id.slice(0, 8)) : '—'}</td>
                  <td style={td}><MonoBadge>{l.action}</MonoBadge></td>
                  <td style={td}>{l.success ? 'ok' : <span style={{ color: '#e74c3c' }}>failed</span>}</td>
                  <td style={{ ...td, fontSize: 12, fontFamily: 'monospace' }}>{l.ip_address || '—'}</td>
                  <td style={{ ...td, fontSize: 11, fontFamily: 'monospace', color: '#6B9E8A', maxWidth: 320, wordBreak: 'break-word' }}>
                    {[l.resource_id && `resource=${l.resource_id.slice(0, 8)}`, l.detail && JSON.stringify(l.detail)].filter(Boolean).join(' ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div style={{ display: 'flex', gap: 8, marginTop: '1rem' }}>
        <Button variant="secondary" style={smallBtn} disabled={offset === 0} onClick={() => { setLoading(true); setOffset(Math.max(0, offset - PAGE)) }}>← Newer</Button>
        <Button variant="secondary" style={smallBtn} disabled={logs.length < PAGE} onClick={() => { setLoading(true); setOffset(offset + PAGE) }}>Older →</Button>
      </div>
    </>
  )
}
