// E/M suggestion for outpatient visits. Without a CPT license the server sends a
// level and MDM reasoning only (cpt_code is null) — never a CPT code or descriptor.

const ELEMENT_LABELS = { problems: 'Problems addressed', data: 'Data reviewed / analyzed', risk: 'Risk of management' }

export default function EmLevelCard({ em }) {
  const levelText = `Level ${em.level} — ${em.patient_type} patient`
  return (
    <div data-testid="em-level-card" style={{ background: 'rgba(155,89,182,0.06)', border: '1px solid rgba(155,89,182,0.25)', borderRadius: 10, padding: '14px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '2px', color: '#b07cc6' }}>
          E/M suggestion · {em.review_label}
        </span>
        <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#6B9E8A' }}>{Math.round(em.confidence * 100)}%</span>
      </div>
      <p style={{ fontSize: 15, fontWeight: 600, color: '#e8f0eb', marginBottom: 2 }}>
        {em.cpt_code ? `${em.cpt_code} · ` : ''}{levelText}
      </p>
      <p style={{ fontSize: 12, color: '#7a9985', marginBottom: 10 }}>
        Basis: {em.basis === 'time' ? `total time (${em.total_time_minutes} min)` : `MDM — ${em.mdm_level}`}
        {em.modifiers.length > 0 && <> · Modifier {em.modifiers.join(', ')}</>}
      </p>
      {em.basis === 'mdm' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {Object.entries(ELEMENT_LABELS).map(([key, label]) => (
            <div key={key} style={{ fontSize: 12 }}>
              <span style={{ color: '#e8f0eb' }}>{label}: </span>
              <span style={{ color: '#b07cc6', textTransform: 'capitalize' }}>{em[key].level}</span>
              <p style={{ color: '#6B9E8A', fontStyle: 'italic', marginTop: 2 }}>{em[key].support}</p>
            </div>
          ))}
        </div>
      )}
      {!em.consistent && (
        <p data-testid="em-inconsistent" style={{ fontSize: 12, color: '#f39c12', marginTop: 10 }}>
          ⚠ {em.consistency_notes.join(' ')}
        </p>
      )}
    </div>
  )
}
