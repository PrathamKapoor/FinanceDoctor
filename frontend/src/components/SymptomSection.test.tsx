import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SymptomSection, SymptomCard } from './SymptomSection'
import { healthFixture, symptomFixture } from '../test/fixtures'

describe('SymptomSection', () => {
  it('renders backend anomaly metrics', () => {
    render(<SymptomSection symptom={symptomFixture} />)
    expect(screen.getByText('PAYMENT HEALTH INCIDENT DETECTED')).toBeInTheDocument()
    expect(screen.getByText('4.54%')).toBeInTheDocument() // baseline
    expect(screen.getByText('21.75%')).toBeInTheDocument() // current
    expect(screen.getByText('3.79×')).toBeInTheDocument() // increase
    expect(screen.getByText('10.854')).toBeInTheDocument() // anomaly score
  })
})

describe('SymptomCard', () => {
  it('renders incident type and affected method', () => {
    render(<SymptomCard symptom={symptomFixture} health={healthFixture} />)
    expect(screen.getByText('Payment method failure spike')).toBeInTheDocument()
    expect(screen.getAllByText('UPI').length).toBeGreaterThan(0)
  })
})