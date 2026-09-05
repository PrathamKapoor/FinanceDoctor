import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApprovalSection } from './ApprovalSection'
import type { ApprovalView } from '../api/types'

const pending = (): ApprovalView => ({
  approval_id: 'apr_1',
  action_id: 'act_1',
  status: 'PENDING',
  requested_at: '2026-08-01T00:00:00',
  expires_at: '2026-08-01T01:00:00',
  approved_at: null,
  rejected_at: null,
  decision_reason: null,
  decided_by: null,
  expired: false,
})

describe('ApprovalSection', () => {
  it('presents the human approval gate and warns that a human must approve', () => {
    render(<ApprovalSection approval={pending()} busy={false} onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.getByText('Human approval required')).toBeInTheDocument()
    expect(screen.getByText(/A human must explicitly approve/)).toBeInTheDocument()
  })

  it('calls onApprove when the human approves', async () => {
    const onApprove = vi.fn()
    render(<ApprovalSection approval={pending()} busy={false} onApprove={onApprove} onReject={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Approve treatment/ }))
    expect(onApprove).toHaveBeenCalledOnce()
  })

  it('calls onReject when the human rejects', async () => {
    const onReject = vi.fn()
    render(<ApprovalSection approval={pending()} busy={false} onApprove={vi.fn()} onReject={onReject} />)
    await userEvent.click(screen.getByRole('button', { name: /Reject treatment/ }))
    expect(onReject).toHaveBeenCalledOnce()
  })

  it('hides the approve/reject buttons once decided', () => {
    const approved = { ...pending(), status: 'APPROVED', decided_by: 'reviewer' }
    render(<ApprovalSection approval={approved} busy={false} onApprove={vi.fn()} onReject={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Approve treatment/ })).not.toBeInTheDocument()
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })
})