import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { Card, Input, Button, Alert, Spinner } from '../components/ui'

const SIGNED_OUT_MESSAGES = {
  idle: 'You were signed out after a period of inactivity.',
  expired: 'Your session expired. Please sign in again.',
}

export default function Login() {
  const { login, verifyMfa, signedOutReason } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaToken, setMfaToken] = useState(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const finish = (user) => navigate(user.mfa_enrollment_required ? '/settings' : '/dashboard')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await login(email.trim().toLowerCase(), password)
      if (result.mfaRequired) {
        setMfaToken(result.mfaToken)
        setPassword('')
      } else {
        finish(result.user)
      }
    } catch (err) {
      if (err.response?.status === 429) {
        setError('Too many attempts. Please wait a minute and try again.')
      } else {
        // Generic message — don't reveal whether the account exists or is locked
        setError('Invalid email or password. Accounts lock for 15 minutes after 5 failed attempts.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleMfa = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { user } = await verifyMfa(mfaToken, code.trim())
      finish(user)
    } catch (err) {
      setCode('')
      if (err.response?.data?.detail === 'Invalid verification code.') {
        setError('Invalid verification code.')
      } else {
        // mfa_token expired or account locked: start over
        setMfaToken(null)
        setError('Sign-in expired. Please enter your email and password again.')
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
          <h2 style={{ fontSize: 20, fontWeight: 600, color: '#e8f0eb', marginBottom: '1.5rem' }}>
            {mfaToken ? 'Two-factor verification' : 'Sign in'}
          </h2>

          {!error && signedOutReason && SIGNED_OUT_MESSAGES[signedOutReason] && (
            <div style={{ marginBottom: '1rem' }}><Alert type="info">{SIGNED_OUT_MESSAGES[signedOutReason]}</Alert></div>
          )}
          {error && <div style={{ marginBottom: '1rem' }}><Alert type="error">{error}</Alert></div>}

          {mfaToken ? (
            <form onSubmit={handleMfa} noValidate>
              <Input
                label="6-digit code from your authenticator app"
                value={code}
                onChange={e => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                autoFocus
                required
                data-testid="mfa-code-input"
              />
              <Button
                type="submit"
                disabled={loading || code.trim().length !== 6}
                style={{ width: '100%', marginTop: '0.5rem' }}
                data-testid="mfa-verify-button"
              >
                {loading ? 'Verifying...' : 'Verify'}
              </Button>
            </form>
          ) : (
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
          )}

          <p style={{ textAlign: 'center', marginTop: '1rem', fontSize: 13, color: '#6B9E8A' }}>
            Need an account? Ask your administrator.
          </p>
        </Card>

        <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: 11, color: '#3d5446', fontFamily: 'monospace' }}>
          DreamLogic Solutions LLC · Biloxi, MS
        </p>
      </div>
    </div>
  )
}
