import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EmLevelCard from '../../components/coding/EmLevelCard'

const em = (over = {}) => ({
  patient_type: 'established', level: 4, basis: 'mdm', total_time_minutes: null, modifiers: [],
  confidence: 0.82, mdm_level: 'moderate', computed_level: 4, consistent: true, consistency_notes: [],
  cpt_code: null, review_label: 'For coder review',
  problems: { level: 'moderate', support: 'acute illness with systemic symptoms' },
  data: { level: 'limited', support: 'rapid strep reviewed' },
  risk: { level: 'moderate', support: 'prescription drug management' },
  ...over,
})

describe('EmLevelCard', () => {
  it('shows a level and MDM reasoning, labeled for coder review, with no CPT code', () => {
    const { container } = render(<EmLevelCard em={em()} />)
    expect(screen.getByText(/For coder review/)).toBeInTheDocument()
    expect(screen.getByText(/Level 4 — established patient/)).toBeInTheDocument()
    expect(screen.getByText('prescription drug management')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/992\d\d/)
  })

  it('shows the E/M code when the server provides one (CPT licensed)', () => {
    render(<EmLevelCard em={em({ cpt_code: '99214', modifiers: ['25'] })} />)
    expect(screen.getByText(/99214 · Level 4/)).toBeInTheDocument()
    expect(screen.getByText(/Modifier 25/)).toBeInTheDocument()
  })

  it('warns when the level disagrees with the computed level', () => {
    render(<EmLevelCard em={em({ level: 5, consistent: false, consistency_notes: ["Suggested level 5 doesn't match level 4."] })} />)
    expect(screen.getByTestId('em-inconsistent')).toHaveTextContent("doesn't match level 4")
  })
})
