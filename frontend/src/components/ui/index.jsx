// ─── Shared UI primitives ────────────────────────────────────────────────────

const S = {
  card: {
    background: '#111a16', border: '1px solid #1f2f26',
    borderRadius: 14, padding: '1.5rem',
  },
  label: {
    display: 'block', fontSize: 12, color: '#6B9E8A',
    marginBottom: 6, textTransform: 'uppercase', letterSpacing: '1px',
  },
  input: {
    width: '100%', background: 'rgba(255,255,255,0.04)',
    border: '1px solid #1f2f26', borderRadius: 8,
    color: '#e8f0eb', fontSize: 14, padding: '10px 14px',
    outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
  },
  btn: {
    border: 'none', borderRadius: 10, fontSize: 15,
    fontWeight: 600, padding: '13px 20px', cursor: 'pointer',
    transition: 'all 0.2s', fontFamily: 'inherit',
  },
}

export function Card({ children, style = {} }) {
  return <div style={{ ...S.card, ...style }}>{children}</div>
}

export function Input({ label, error, ...props }) {
  return (
    <div style={{ marginBottom: '1rem' }}>
      {label && <label style={S.label}>{label}</label>}
      <input style={{ ...S.input, ...(error ? { borderColor: 'rgba(231,76,60,0.5)' } : {}) }} {...props} />
      {error && <p style={{ fontSize: 12, color: '#e74c3c', marginTop: 4 }}>{error}</p>}
    </div>
  )
}

export function Button({ children, variant = 'primary', disabled, style = {}, ...props }) {
  const variants = {
    primary: { background: disabled ? '#085041' : '#0D7A5F', color: '#fff' },
    secondary: { background: 'none', border: '1px solid #1f2f26', color: '#6B9E8A' },
    danger: { background: 'rgba(231,76,60,0.15)', border: '1px solid rgba(231,76,60,0.3)', color: '#e74c3c' },
  }
  return (
    <button
      disabled={disabled}
      style={{ ...S.btn, ...variants[variant], ...(disabled ? { cursor: 'not-allowed', opacity: 0.6 } : {}), ...style }}
      {...props}
    >
      {children}
    </button>
  )
}

export function Alert({ type = 'error', children }) {
  const colors = {
    error: { bg: 'rgba(231,76,60,0.1)', border: 'rgba(231,76,60,0.3)', color: '#e74c3c' },
    success: { bg: 'rgba(46,204,113,0.1)', border: 'rgba(46,204,113,0.3)', color: '#2ECC71' },
    info: { bg: 'rgba(13,122,95,0.08)', border: 'rgba(13,122,95,0.2)', color: '#12A07C' },
  }
  const c = colors[type]
  return (
    <div style={{ background: c.bg, border: `1px solid ${c.border}`, borderRadius: 8, padding: '10px 14px', color: c.color, fontSize: 13 }}>
      {children}
    </div>
  )
}

export function Spinner({ size = 20 }) {
  return (
    <span style={{
      display: 'inline-block', width: size, height: size,
      border: '2px solid rgba(255,255,255,0.2)',
      borderTopColor: '#2ECC71', borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
    }} />
  )
}

export function MonoBadge({ children, color = '#2ECC71', bg = 'rgba(46,204,113,0.1)' }) {
  return (
    <span style={{
      fontFamily: 'monospace', fontSize: 12, fontWeight: 600,
      color, background: bg, padding: '3px 10px', borderRadius: 5,
    }}>
      {children}
    </span>
  )
}

export function SectionLabel({ active, children }) {
  return (
    <span style={{
      fontSize: 11, fontFamily: 'monospace', textTransform: 'uppercase',
      letterSpacing: '2px', color: active ? '#2ECC71' : '#3d5446',
    }}>
      {active ? '● ' : '○ '}{children}
    </span>
  )
}

// Global spinner keyframe (injected once)
if (typeof document !== 'undefined' && !document.getElementById('codify-spin')) {
  const style = document.createElement('style')
  style.id = 'codify-spin'
  style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
  document.head.appendChild(style)
}
