import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { Spinner } from '../ui'

/**
 * Requires a signed-in user. `roles` limits the route to those roles.
 * Users who must enroll in MFA are held on /settings until they do.
 * (The API enforces all of this too — this only keeps the UI consistent.)
 */
export default function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spinner size={32} />
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />
  if (user.mfa_enrollment_required && location.pathname !== '/settings') {
    return <Navigate to="/settings" replace />
  }
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />
  return children
}
