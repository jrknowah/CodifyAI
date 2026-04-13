import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Card, Input, Button, Alert, Spinner } from '../components/ui'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email.trim().toLowerCase(), password)
      navigate('/dashboard')
    } catch (err) {
      const msg = err.response?.data?.detail
      if (err.response?.status === 423) {
        setError(msg || 'Account temporarily locked. Try again later.')
      } else {
        // Generic message — don't reveal whether account exists
        setError('Invalid email or password.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0B1F1A', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div style={{ width: '100%', maxWidth: 420 }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <div style={{ width: 40, height: 40, background: '#0D7A5F', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>⚕</div>
            <span style={{ fontFamily: 'Georgia, serif', fontSize: 28, fontWeight: 700, color: '#fff', letterSpacing: '-0.5px' }}>
              Codify<span style={{ color: '#12A07C' }}>AI</span>
            </span>
          </div>
          <p style={{ color: '#6B9E8A', fontSize: 14 }}>Medical coding for post-acute care</p>
        </div>

        <Card>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: '#e8f0eb', marginBottom: '1.5rem' }}>Sign in</h2>

          {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}

          <form onSubmit={handleSubmit} noValidate>
            <Input
              label="Email address"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@facility.com"
              required
              autoComplete="email"
              data-testid="email-input"
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••••••"
              required
              autoComplete="current-password"
              data-testid="password-input"
            />

            <Button
              type="submit"
              disabled={loading}
              style={{ width: '100%', marginTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
              data-testid="login-button"
            >
              {loading ? <><Spinner size={16} /> Signing in...</> : 'Sign in'}
            </Button>
          </form>

          <p style={{ textAlign: 'center', marginTop: '1rem', fontSize: 13, color: '#6B9E8A' }}>
            Need an account?{' '}
            <Link to="/register" style={{ color: '#12A07C', textDecoration: 'none' }}>Register</Link>
          </p>
        </Card>

        <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: 11, color: '#3d5446', fontFamily: 'monospace' }}>
          DreamLogic Solutions LLC · Biloxi, MS
        </p>
      </div>
    </div>
  )
}
