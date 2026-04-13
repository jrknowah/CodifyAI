import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { Card, Input, Button, Alert, Spinner } from '../components/ui'

const PASSWORD_RULES = [
  { test: v => v.length >= 12,          label: '12+ characters' },
  { test: v => /[A-Z]/.test(v),         label: 'Uppercase letter' },
  { test: v => /[0-9]/.test(v),         label: 'Number' },
  { test: v => /[^A-Za-z0-9]/.test(v),  label: 'Special character' },
]

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }))

  const validate = () => {
    const errs = {}
    if (!form.email.includes('@')) errs.email = 'Enter a valid email.'
    if (form.full_name.trim().length < 2) errs.full_name = 'Name must be at least 2 characters.'
    const failedRules = PASSWORD_RULES.filter(r => !r.test(form.password))
    if (failedRules.length) errs.password = `Password needs: ${failedRules.map(r => r.label).join(', ')}.`
    return errs
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const errs = validate()
    setErrors(errs)
    if (Object.keys(errs).length) return

    setServerError('')
    setLoading(true)
    try {
      await authApi.register(form)
      navigate('/login', { state: { registered: true } })
    } catch (err) {
      setServerError(err.response?.data?.detail || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0B1F1A', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div style={{ width: '100%', maxWidth: 440 }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <span style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#fff' }}>
            Codify<span style={{ color: '#12A07C' }}>AI</span>
          </span>
        </div>

        <Card>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: '#e8f0eb', marginBottom: '1.5rem' }}>Create account</h2>

          {serverError && <div style={{ marginBottom: '1rem' }}><Alert type="error">{serverError}</Alert></div>}

          <form onSubmit={handleSubmit} noValidate>
            <Input label="Full name" type="text" value={form.full_name} onChange={set('full_name')} placeholder="Jane Smith" error={errors.full_name} required data-testid="name-input" />
            <Input label="Email address" type="email" value={form.email} onChange={set('email')} placeholder="you@facility.com" error={errors.email} required data-testid="email-input" />
            <Input label="Password" type="password" value={form.password} onChange={set('password')} placeholder="Min. 12 characters" error={errors.password} required data-testid="password-input" />

            {/* Password strength indicator */}
            <div style={{ display: 'flex', gap: 6, marginBottom: '1rem', marginTop: -8 }}>
              {PASSWORD_RULES.map((r, i) => (
                <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: r.test(form.password) ? '#2ECC71' : '#1f2f26', transition: 'background 0.2s' }} />
              ))}
            </div>

            <Button type="submit" disabled={loading} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              {loading ? <><Spinner size={16} /> Creating account...</> : 'Create account'}
            </Button>
          </form>

          <p style={{ textAlign: 'center', marginTop: '1rem', fontSize: 13, color: '#6B9E8A' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: '#12A07C', textDecoration: 'none' }}>Sign in</Link>
          </p>
        </Card>
      </div>
    </div>
  )
}
