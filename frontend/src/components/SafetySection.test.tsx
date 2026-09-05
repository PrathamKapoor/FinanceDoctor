import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SafetySection } from './SafetySection'
import { passingPolicyFixture, rejectedPolicyFixture } from '../test/fixtures'

describe('SafetySection', () => {
  it('renders every policy check as passed', () => {
    render(<SafetySection policy={passingPolicyFixture} />)
    expect(screen.getByText('All checks passed')).toBeInTheDocument()
    expect(screen.getByText('Action is allowlisted')).toBeInTheDocument()
    expect(screen.getByText('All targets are eligible')).toBeInTheDocument()
    expect(screen.getByText('Action integrity verified')).toBeInTheDocument()
  })

  it('shows a failed check and marks the decision as blocked', () => {
    render(<SafetySection policy={rejectedPolicyFixture} />)
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText(/Recovery amount exceeds limit/)).toBeInTheDocument()
    expect(screen.getByText('Rejected')).toBeInTheDocument()
  })
})