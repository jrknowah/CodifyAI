import { useState } from 'react'
import { codingApi } from '../services/api'
import EmLevelCard from '../components/coding/EmLevelCard'
import Sidebar from '../components/layout/Sidebar'
import { Card, Button, Alert, SectionLabel, MonoBadge, Spinner } from '../components/ui'

const SAMPLES = {
  'Strep (Urgent Care)': `Established patient, 34-year-old female, presents with 3 days of sore throat, fever to 101.4F, and painful swallowing. No cough. Exam: tonsillar exudates, tender anterior cervical lymphadenopathy. Rapid strep antigen ordered and reviewed: positive. Assessment: streptococcal pharyngitis. Plan: amoxicillin 500 mg PO BID x 10 days, ibuprofen as needed, return if unable to tolerate fluids. Total time 25 minutes.`,
  'Hip Replacement': `Patient is a 74-year-old male, POD #12 following right total hip arthroplasty. Admitted to recuperative care for skilled nursing and PT. PMH: essential hypertension (controlled on lisinopril), type 2 diabetes mellitus (HbA1c 7.1%), hyperlipidemia. Currently ambulating 50 feet with rolling walker, pain 3/10, wound healing without erythema or drainage. Continue DVT prophylaxis with enoxaparin. Blood glucose monitoring BID, values within target range.`,
  'Stroke Recovery': `Patient is a 68-year-old female recovering from left MCA ischemic stroke 3 weeks prior. Right-sided hemiparesis strength 3/5, expressive aphasia improving. PMH: atrial fibrillation on apixaban, hypertension, GERD. Transfers with minimal assist, sitting balance good, standing balance fair. Speech intelligibility approximately 70%. Dysphagia screen passed. Continue anticoagulation. Fall prevention protocol in place.`,
  'Wound Care':      `Patient is an 82-year-old female with stage III pressure ulcer to the right sacral region. PMH: type 2 diabetes with peripheral neuropathy, obesity BMI 36, hypertension, vascular dementia moderate stage. Wound measures 4.2cm x 3.8cm x 1.1cm with pink granulation tissue and minimal serous exudate. Wound care BID with collagenase ointment and non-adherent dressing. High-protein supplement ordered.`,
}

const TYPE_STYLES = {
  'ICD-10-CM': { bg: 'rgba(52,152,219,0.12)', color: '#3498db' },
  'CPT':    { bg: 'rgba(155,89,182,0.12)', color: '#9b59b6' },
  'HCPCS':  { bg: 'rgba(230,126,34,0.12)', color: '#e67e22' },
}

export default function Dashboard() {
  const [note, setNote] = useState('')
  const [facilityType, setFacilityType] = useState('post-acute')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const analyze = async () => {
    if (!note.trim() || loading) return
    setError('')
    setLoading(true)
    setResult(null)
    try {
      const res = await codingApi.analyze(note, facilityType)
      setResult(res.data)
    } catch (err) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 429) {
        setError('Too many requests. Please wait a moment and try again.')
      } else if (err.response?.status === 403) {
        setError('Your account has view-only access. Ask an administrator for coder access to run analyses.')
      } else {
        // 422 validation errors arrive as a list, not a string
        setError(typeof detail === 'string' ? detail : detail?.[0]?.msg || 'Analysis failed. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') analyze()
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <main style={{ flex: 1, padding: '2rem', overflowY: 'auto', maxWidth: 'calc(100vw - 224px)' }}>

        <div style={{ marginBottom: '1.75rem' }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 26, fontWeight: 700, color: '#e8f0eb', marginBottom: 4 }}>
            Code Analyzer
          </h1>
          <p style={{ color: '#6B9E8A', fontSize: 14 }}>
            Paste a signed visit note to generate ICD-10-CM and HCPCS suggestions (plus an E/M level for urgent care). <kbd style={{ fontSize: 11, background: '#1f2f26', borderRadius: 4, padding: '2px 6px', color: '#6B9E8A' }}>Ctrl+Enter</kbd> to analyze.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', alignItems: 'start' }}>

          {/* Input panel */}
          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <SectionLabel active>Clinical note input</SectionLabel>
              <select
                value={facilityType}
                onChange={e => setFacilityType(e.target.value)}
                data-testid="facility-select"
                style={{ background: '#0a0f0d', border: '1px solid #1f2f26', borderRadius: 6, color: '#7a9985', fontSize: 12, padding: '4px 8px', cursor: 'pointer', fontFamily: 'inherit' }}
              >
                <option value="post-acute">Post-Acute / Recuperative</option>
                <option value="snf">Skilled Nursing Facility</option>
                <option value="home-health">Home Health</option>
                <option value="irf">Inpatient Rehab (IRF)</option>
                <option value="urgent-care">Urgent Care</option>
              </select>
            </div>

            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Paste clinical note here (min. 30 characters)..."
              rows={10}
              data-testid="note-input"
              style={{
                width: '100%', background: 'rgba(255,255,255,0.03)', border: '1px solid #1f2f26',
                borderRadius: 10, color: '#e8f0eb', fontSize: 14, lineHeight: 1.7,
                padding: '14px', outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                fontFamily: 'inherit', minHeight: 200,
              }}
            />

            <div style={{ fontSize: 11, color: note.length > 9500 ? '#e74c3c' : '#3d5446', textAlign: 'right', marginTop: 4, fontFamily: 'monospace' }}>
              {note.length.toLocaleString()} / 10,000
            </div>

            {/* Sample loaders */}
            <div style={{ display: 'flex', gap: 8, marginTop: '0.75rem', flexWrap: 'wrap' }}>
              {Object.keys(SAMPLES).map(k => (
                <button key={k} onClick={() => { setNote(SAMPLES[k]); setError(''); if (k.includes('Urgent Care')) setFacilityType('urgent-care') }}
                  style={{ background: 'none', border: '1px solid #1f2f26', borderRadius: 6, color: '#6B9E8A', fontSize: 11, fontFamily: 'monospace', padding: '4px 10px', cursor: 'pointer' }}>
                  {k}
                </button>
              ))}
            </div>

            {error && <div style={{ marginTop: '0.75rem' }}><Alert type="error">{error}</Alert></div>}

            <Button
              onClick={analyze}
              disabled={loading || note.trim().length < 30}
              style={{ width: '100%', marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
              data-testid="analyze-button"
            >
              {loading ? <><Spinner size={16} /> Analyzing...</> : '⚡ Analyze & Generate Codes'}
            </Button>
          </Card>

          {/* Results panel */}
          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <SectionLabel active={!!result}>
                {result ? `${result.code_count} codes found` : 'Suggested codes'}
              </SectionLabel>
              {result && (
                <span style={{ fontSize: 10, color: '#3d5446', fontFamily: 'monospace' }}>
                  {new Date(result.created_at).toLocaleTimeString()}
                </span>
              )}
            </div>

            {!result && !loading && (
              <div style={{ minHeight: 280, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, color: '#3d5446', fontSize: 13, border: '1px dashed #1f2f26', borderRadius: 10 }}>
                <span style={{ fontSize: 32, opacity: 0.3 }}>📄</span>
                Results will appear here
              </div>
            )}

            {loading && (
              <div style={{ minHeight: 280, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
                <Spinner size={36} />
                <p style={{ color: '#6B9E8A', fontSize: 13 }}>Processing clinical note...</p>
              </div>
            )}

            {result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="results-container">
                {result.codes.map((c, i) => {
                  const ts = TYPE_STYLES[c.type] || { bg: 'rgba(255,255,255,0.05)', color: '#aaa' }
                  return (
                    <div key={i} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1f2f26', borderRadius: 10, padding: '14px 16px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <MonoBadge>{c.code}{c.modifiers?.length ? `-${c.modifiers.join('-')}` : ''}</MonoBadge>
                        <span style={{ fontSize: 10, fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '1.5px', padding: '3px 8px', borderRadius: 4, background: ts.bg, color: ts.color }}>
                          {c.type}
                        </span>
                      </div>
                      <p style={{ fontSize: 13, color: '#e8f0eb', marginBottom: 4, lineHeight: 1.5 }}>{c.description}</p>
                      <p style={{ fontSize: 12, color: '#6B9E8A', fontStyle: 'italic', marginBottom: 8 }}>{c.reason}</p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ flex: 1, height: 3, background: '#1f2f26', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${Math.round(c.confidence * 100)}%`, background: 'linear-gradient(90deg, #085041, #2ECC71)', borderRadius: 2 }} />
                        </div>
                        <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#6B9E8A', whiteSpace: 'nowrap' }}>
                          {Math.round(c.confidence * 100)}%
                        </span>
                      </div>
                    </div>
                  )
                })}

                {result.em_level && <EmLevelCard em={result.em_level} />}

                {result.flagged_codes?.length > 0 && (
                  <div data-testid="flagged-codes" style={{ border: '1px solid rgba(243,156,18,0.3)', borderRadius: 10, padding: '10px 16px', fontSize: 12, color: '#f39c12' }}>
                    <p style={{ fontSize: 10, fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '2px', marginBottom: 4 }}>Removed by validation</p>
                    {result.flagged_codes.map((f, i) => (
                      <p key={i}>{f.code ? `${f.code} (${f.type})` : f.type}: {f.issue}</p>
                    ))}
                  </div>
                )}

                <div style={{ background: 'rgba(13,122,95,0.08)', border: '1px solid rgba(13,122,95,0.2)', borderRadius: 10, padding: '14px 16px' }}>
                  <p style={{ fontSize: 10, fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '2px', color: '#12A07C', marginBottom: 6 }}>Clinical Rationale</p>
                  <p style={{ fontSize: 13, color: '#7a9985', lineHeight: 1.6 }}>{result.summary}</p>
                </div>

                <p style={{ fontSize: 10, fontFamily: 'monospace', color: '#3d5446', textAlign: 'right' }}>
                  {result.encounter_id?.toString().slice(0, 8)} · {result.model_used}
                </p>
              </div>
            )}
          </Card>
        </div>
      </main>
    </div>
  )
}
