import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'

const NAV = [
  { to: '/dashboard', icon: '⚡', label: 'Code Analyzer' },
  { to: '/history',   icon: '📋', label: 'Encounter History' },
  { to: '/settings',  icon: '⚙️', label: 'Settings' },
]
const ADMIN_NAV = { to: '/admin', icon: '🛡️', label: 'Admin' }

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <aside style={{
      width: 224, minHeight: '100vh', background: '#080f0c',
      borderRight: '1px solid #1f2f26', display: 'flex',
      flexDirection: 'column', padding: '1.5rem 0', flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '0 1.25rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 32, height: 32, background: '#0D7A5F', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>
            ⚕
          </div>
          <span style={{ fontFamily: 'Georgia, serif', fontSize: 20, fontWeight: 700, color: '#fff' }}>
            Codify<span style={{ color: '#12A07C' }}>AI</span>
          </span>
        </div>
        <p style={{ fontSize: 10, color: '#3d5446', marginTop: 4, marginLeft: 40, fontFamily: 'monospace', letterSpacing: '1px' }}>
          v0.2.0
        </p>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, padding: '0 0.75rem' }}>
        {(user?.role === 'admin' ? [...NAV, ADMIN_NAV] : NAV).map(({ to, icon, label }) => (
          <NavLink key={to} to={to} style={({ isActive }) => ({
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 12px', borderRadius: 8, marginBottom: 4,
            fontSize: 14, fontWeight: isActive ? 600 : 400,
            color: isActive ? '#2ECC71' : '#7a9985',
            background: isActive ? 'rgba(46,204,113,0.08)' : 'transparent',
            textDecoration: 'none', transition: 'all 0.15s',
          })}>
            <span style={{ fontSize: 15 }}>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User info + logout */}
      <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid #1f2f26' }}>
        <div style={{ background: 'rgba(13,122,95,0.08)', borderRadius: 8, padding: '10px 12px', marginBottom: '0.75rem' }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: '#e8f0eb', marginBottom: 2 }}>{user?.full_name}</p>
          <p style={{ fontSize: 11, color: '#6B9E8A', wordBreak: 'break-all' }}>{user?.email}</p>
          <p style={{ fontSize: 10, color: '#3d5446', marginTop: 4, textTransform: 'uppercase', letterSpacing: '1px' }}>{user?.role}</p>
        </div>
        <button onClick={handleLogout} style={{
          width: '100%', background: 'none', border: '1px solid #1f2f26',
          borderRadius: 8, color: '#6B9E8A', fontSize: 13, padding: '8px',
          cursor: 'pointer', fontFamily: 'inherit',
        }}>
          Sign out
        </button>
      </div>
    </aside>
  )
}
