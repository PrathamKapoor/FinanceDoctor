import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DiagnosisSection } from './DiagnosisSection'
import { diagnosisFixture } from '../test/fixtures'

describe('DiagnosisSection', () => {
  it('renders the leading diagnosis and action', () => {
    render(<DiagnosisSection diagnosis={diagnosisFixture} />)
    expect(screen.getAllByText('PAYMENT METHOD DEGRADATION').length).toBeGreaterThan(0)
    expect(screen.getByText('CREATE PAYMENT LINK')).toBeInTheDocument()
  })

  it('labels confidence as model assessment rather than a percentage', () => {
    render(<DiagnosisSection diagnosis={diagnosisFixture} />)
    expect(screen.getByText('High confidence')).toBeInTheDocument()
    expect(screen.queryByText(/91%/)).not.toBeInTheDocument()
  })

  it('renders differential alternatives with reasons', () => {
    render(<DiagnosisSection diagnosis={diagnosisFixture} />)
    expect(screen.getByText(/GENERAL PAYMENT FAILURE/)).toBeInTheDocument()
    expect(screen.getByText(/CUSTOMER BEHAVIOR CHANGE/)).toBeInTheDocument()
  })

  it('renders evidence explorer rows with deterministic evidence IDs', () => {
    render(<DiagnosisSection diagnosis={diagnosisFixture} />)
    expect(screen.getByText(/Evidence explorer/)).toBeInTheDocument()
    expect(screen.getByText('payment_method.UPI.failure_rate')).toBeInTheDocument()
    expect(screen.getByText('anomaly.payment_failure_rate')).toBeInTheDocument()
  })
})