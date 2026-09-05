import type { ApprovalView } from '../api/types'
import { formatDateTime } from '../lib/format'
import { Section } from './Section'
import { approvalTone } from '../lib/status'

export function ApprovalSection({
  approval,
  busy,
  error,
  onApprove,
  onReject,
}: {
  approval: ApprovalView
  busy: boolean
  error?: string | null
  onApprove: () => void
  onReject: () => void
}) {
  const pending = approval.status === 'PENDING'
  return (
    <Section
      kicker="Stage 4 — human approval boundary"
      title="Human approval"
      step={6}
      status={approval.status}
      statusTone={approvalTone(approval.status)}
    >
      {pending ? (
        <div className="approvalGate">
          <h3 className="approvalGate__title">Human approval required</h3>
          <p className="approvalGate__body">
            The AI recommended this treatment and the deterministic policy engine validated it.
            A human must explicitly approve the exact immutable action before any Razorpay
            operation is executed.
          </p>
          <ol className="approvalGate__steps">
            <li>
              <strong>AI recommended</strong>
              <span>a bounded recovery treatment from the diagnosis</span>
            </li>
            <li>
              <strong>Policy validated</strong>
              <span>deterministic checks passed on an immutable snapshot</span>
            </li>
            <li>
              <strong>You decide</strong>
              <span>approve to authorize execution — or reject to stop it</span>
            </li>
          </ol>
          <div className="approvalGate__flow">
            AI reasons → policy constrains → <strong>human approves</strong> → Razorpay acts →
            system measures
          </div>
          <div className="approvalGate__actions">
            <button className="btn btn--primary" onClick={onApprove} disabled={busy}>
              {busy ? 'Approving…' : 'Approve treatment'}
            </button>
            <button className="btn btn--danger" onClick={onReject} disabled={busy}>
              {busy ? 'Rejecting…' : 'Reject treatment'}
            </button>
          </div>
          {error ? (
            <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 12 }}>{error}</p>
          ) : null}
        </div>
      ) : (
        <div>
          <p style={{ marginTop: 0, fontSize: 14 }}>
            Approval request <span className="mono">{approval.approval_id}</span> has been decided
            by <strong>{approval.decided_by ?? 'unknown'}</strong>.
          </p>
          <div className="statGrid statGrid--2" style={{ maxWidth: 520 }}>
            <div className="stat">
              <div className="stat__label">Requested</div>
              <div className="stat__value" style={{ fontSize: 14 }}>
                {formatDateTime(approval.requested_at)}
              </div>
            </div>
            <div className="stat">
              <div className="stat__label">Decided by</div>
              <div className="stat__value" style={{ fontSize: 14 }}>
                {approval.decided_by ?? '—'}
              </div>
            </div>
          </div>
          {approval.decision_reason ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              Reason: {approval.decision_reason}
            </p>
          ) : null}
        </div>
      )}
    </Section>
  )
}