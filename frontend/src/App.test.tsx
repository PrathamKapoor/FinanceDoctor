import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'
import { api } from './api/client'
import type { CaseView, ApprovalView, TreatmentView, OutcomeView } from './api/types'
import { makeCaseView } from './test/fixtures'

vi.mock('./api/client', () => ({
  api: {
    getHealth: vi.fn(),
    startCase: vi.fn(),
    getCase: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    execute: vi.fn(),
    simulate: vi.fn(),
  },
}))

const stubHealth = {
  status: 'ok',
  version: '0.6.0',
  environment: 'development',
  razorpay_mode: 'stub',
  speech_provider: 'stub',
  consultation: 'stub',
  world_loaded: false,
}

const liveHealth = {
  ...stubHealth,
  razorpay_mode: 'live',
  speech_provider: 'minimax',
  consultation: 'live',
}

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>

const approvalPending: ApprovalView = {
  approval_id: 'apr_1',
  action_id: 'act_test',
  status: 'PENDING',
  requested_at: '2026-08-01T00:00:00',
  expires_at: '2026-08-01T01:00:00',
  approved_at: null,
  rejected_at: null,
  decision_reason: null,
  decided_by: null,
  expired: false,
}

const approvalApproved: ApprovalView = { ...approvalPending, status: 'APPROVED', decided_by: 'human_reviewer' }

const treatment: TreatmentView = {
  execution_id: 'exe_1',
  action_id: 'act_test',
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

const outcome: OutcomeView = {
  outcome_id: 'out_1',
  status: 'PARTIALLY_RECOVERED',
  targets_total: 78,
  targets_pending: 22,
  targets_succeeded: 55,
  targets_failed: 0,
  targets_expired: 1,
  amount_targeted_minor: 8700000,
  amount_recovered_minor: 6200000,
  conversion_rate: 0.705,
  currency: 'INR',
  finalized: false,
  effectiveness: {
    intervention_outcome_id: 'out_1',
    targets_total: 78,
    targets_recovered: 55,
    targets_pending: 22,
    targets_unrecovered: 1,
    currency: 'INR',
    amount_targeted_minor: 8700000,
    amount_recovered_minor: 6200000,
    amount_remaining_minor: 2500000,
    recovery_rate: 0.705,
    revenue_recovery_rate: 0.713,
    time_to_first_recovery_seconds: 30,
    time_to_last_recovery_seconds: 90,
    computed_at: '2026-08-01T00:00:00',
  },
}

const outcomePending: OutcomeView = { ...outcome, status: 'PENDING', targets_succeeded: 0, amount_recovered_minor: 0, conversion_rate: 0, finalized: false }

function baseCase(): CaseView {
  return makeCaseView({ approval: approvalPending })
}

beforeEach(() => {
  vi.resetAllMocks()
  mocked.getHealth.mockResolvedValue(stubHealth)
  mocked.startCase.mockResolvedValue(baseCase())
})

describe('App — provider mode visibility', () => {
  it('shows stub badges and demo environment from health', async () => {
    render(<App />)
    await screen.findByText('PAYMENT HEALTH INCIDENT DETECTED')
    expect(screen.getByText('Razorpay: Stub')).toBeInTheDocument()
    expect(screen.getByText('AI: Stub')).toBeInTheDocument()
    expect(screen.getByText('Speech: Stub')).toBeInTheDocument()
    expect(screen.getByText('Demo environment')).toBeInTheDocument()
  })

  it('shows live badges and integration mode when providers are live', async () => {
    mocked.getHealth.mockResolvedValue(liveHealth)
    render(<App />)
    await screen.findByText('PAYMENT HEALTH INCIDENT DETECTED')
    expect(screen.getByText('Razorpay: Live API')).toBeInTheDocument()
    expect(screen.getByText('AI: Live MiniMax')).toBeInTheDocument()
    expect(screen.getByText('Speech: Live MiniMax')).toBeInTheDocument()
    expect(screen.getByText('Integration mode')).toBeInTheDocument()
  })
})

describe('App — case journey rendering', () => {
  it('renders incident metrics, diagnosis, policy, and approval gate from backend data', async () => {
    render(<App />)
    await screen.findByText('PAYMENT HEALTH INCIDENT DETECTED')
    expect(screen.getByText('10.854')).toBeInTheDocument()
    expect(screen.getAllByText('PAYMENT METHOD DEGRADATION').length).toBeGreaterThan(0)
    expect(screen.getByText('Human approval required')).toBeInTheDocument()
    expect(screen.getByText('Action is allowlisted')).toBeInTheDocument()
  })
})

describe('App — full demo journey', () => {
  it('drives approve → execute → simulate through the mocked backend', async () => {
    mocked.approve.mockResolvedValue(makeCaseView({ approval: approvalApproved }))
    mocked.execute.mockResolvedValue(
      makeCaseView({ approval: approvalApproved, treatment, outcome: outcomePending }),
    )
    mocked.simulate.mockResolvedValue(
      makeCaseView({ approval: approvalApproved, treatment, outcome }),
    )

    render(<App />)
    await screen.findByText('Human approval required')

    await userEvent.click(screen.getByRole('button', { name: /Approve treatment/ }))
    await waitFor(() => expect(mocked.approve).toHaveBeenCalledOnce())
    await screen.findByRole('button', { name: /Execute treatment/ })

    await userEvent.click(screen.getByRole('button', { name: /Execute treatment/ }))
    await waitFor(() => expect(mocked.execute).toHaveBeenCalledOnce())
    await screen.findByRole('button', { name: /Simulate provider webhook/ })

    await userEvent.click(screen.getByRole('button', { name: /Simulate provider webhook/ }))
    await waitFor(() => expect(mocked.simulate).toHaveBeenCalledOnce())
    // The recovery status appears in both the Outcome section and the Case summary.
    expect((await screen.findAllByText('Partially Recovered')).length).toBeGreaterThan(0)
  })
})