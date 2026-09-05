import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OutcomeSection } from './OutcomeSection'
import { TreatmentSection } from './TreatmentSection'
import type { OutcomeView, TreatmentView } from '../api/types'

function outcome(status: string): OutcomeView {
  return {
    outcome_id: 'out_1',
    status,
    targets_total: 10,
    targets_pending: 2,
    targets_succeeded: 7,
    targets_failed: 0,
    targets_expired: 1,
    amount_targeted_minor: 10000,
    amount_recovered_minor: 7000,
    conversion_rate: 0.7,
    currency: 'INR',
    finalized: status === 'RECOVERED',
    effectiveness: {
      intervention_outcome_id: 'out_1',
      targets_total: 10,
      targets_recovered: 7,
      targets_pending: 2,
      targets_unrecovered: 1,
      currency: 'INR',
      amount_targeted_minor: 10000,
      amount_recovered_minor: 7000,
      amount_remaining_minor: 3000,
      recovery_rate: 0.7,
      revenue_recovery_rate: 0.7,
      time_to_first_recovery_seconds: 30,
      time_to_last_recovery_seconds: 90,
      computed_at: '2026-08-01T00:00:00',
    },
  }
}

describe('OutcomeSection', () => {
  it('renders recovered revenue and recovery rate for partial recovery', () => {
    render(<OutcomeSection outcome={outcome('PARTIALLY_RECOVERED')} canSimulate={false} busy={false} onSimulate={() => {}} />)
    expect(screen.getByText('Partially Recovered')).toBeInTheDocument()
    expect(screen.getByText('Recovered revenue')).toBeInTheDocument()
    expect(screen.getByText('Recovery rate')).toBeInTheDocument()
    expect(screen.getByText('70.00%')).toBeInTheDocument()
  })

  it('renders pending state with unrecovered breakdown', () => {
    render(<OutcomeSection outcome={outcome('PENDING')} canSimulate={true} busy={false} onSimulate={() => {}} />)
    expect(screen.getByText('Pending')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Simulate provider webhook/ })).toBeInTheDocument()
  })

  it('labels demo simulation honestly and drops it in live mode', () => {
    const pending = outcome('PENDING')
    const { rerender } = render(
      <OutcomeSection outcome={pending} canSimulate={false} busy={false} onSimulate={() => {}} />,
    )
    expect(screen.getByText('Demo simulation')).toBeInTheDocument()
    expect(screen.getByText(/no real money moved/)).toBeInTheDocument()
    rerender(
      <OutcomeSection
        outcome={pending}
        canSimulate={false}
        busy={false}
        onSimulate={() => {}}
        demoMode={false}
      />,
    )
    expect(screen.queryByText('Demo simulation')).not.toBeInTheDocument()
    expect(screen.queryByText(/no real money moved/)).not.toBeInTheDocument()
  })
})

describe('TreatmentSection', () => {
  it('renders a successful execution', () => {
    const t: TreatmentView = {
      execution_id: 'exe_1',
      action_id: 'act_1',
      status: 'SUCCEEDED',
      provider: 'razorpay',
      provider_operation: 'create_payment_link',
      provider_reference: 'plink_abc',
      links_count: 78,
      started_at: '2026-08-01T00:00:00',
      completed_at: '2026-08-01T00:00:01',
      error_code: null,
      error_message: null,
    }
    render(<TreatmentSection treatment={t} />)
    expect(screen.getByText('Succeeded')).toBeInTheDocument()
    expect(screen.getByText('78')).toBeInTheDocument()
  })

  it('makes a failed execution visible', () => {
    const t: TreatmentView = {
      execution_id: 'exe_2',
      action_id: 'act_1',
      status: 'FAILED',
      provider: 'razorpay',
      provider_operation: 'create_payment_link',
      provider_reference: null,
      links_count: 0,
      started_at: '2026-08-01T00:00:00',
      completed_at: null,
      error_code: 'ExecutionError',
      error_message: 'Adapter returned no payment links',
    }
    render(<TreatmentSection treatment={t} />)
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText(/Adapter returned no payment links/)).toBeInTheDocument()
  })

  it('marks simulated treatment explicitly, and drops the mark in live mode', () => {
    const t: TreatmentView = {
      execution_id: 'exe_1',
      action_id: 'act_1',
      status: 'SUCCEEDED',
      provider: 'razorpay',
      provider_operation: 'create_payment_link',
      provider_reference: 'plink_abc',
      links_count: 78,
      started_at: '2026-08-01T00:00:00',
      completed_at: '2026-08-01T00:00:01',
      error_code: null,
      error_message: null,
    }
    const { rerender } = render(<TreatmentSection treatment={t} />)
    expect(screen.getByText('Demo simulation')).toBeInTheDocument()
    expect(screen.getByText(/no real transaction/)).toBeInTheDocument()
    expect(screen.getByText(/Creating Payment Link \(simulated\)/)).toBeInTheDocument()
    rerender(<TreatmentSection treatment={t} demoMode={false} />)
    expect(screen.queryByText('Demo simulation')).not.toBeInTheDocument()
  })
})