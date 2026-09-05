import type { CaseView } from '../api/types'
import { formatRupees } from '../lib/format'
import { Section } from './Section'

export function CaseSummary({ data, demoMode = true }: { data: CaseView; demoMode?: boolean }) {
  const symptom = data.symptom?.incident_type ?? 'Payment failure spike'
  const diagnosis = data.diagnosis?.leading_hypothesis?.replaceAll('_', ' ') ?? 'Pending'
  const prescription = data.prescription?.action_type?.replaceAll('_', ' ') ?? 'Pending'
  const approval = data.approval?.status ?? 'Pending'
  const safety = data.policy
    ? data.policy.decision === 'REJECTED'
      ? 'Policy-rejected'
      : 'Human-approved, policy-validated'
    : 'Pending'
  const outcome = data.outcome?.status ?? 'Pending'
  const recovered = data.outcome ? formatRupees(data.outcome.amount_recovered_minor) : '—'

  return (
    <Section kicker="End-to-end" title="Financial case summary" step={8} status={outcome} statusTone="muted">
      <div className="summary">
        <div className="summaryCell">
          <div className="summaryCell__label">Symptom</div>
          <div className="summaryCell__value">{symptom.replaceAll('_', ' ')}</div>
        </div>
        <div className="summaryCell">
          <div className="summaryCell__label">Diagnosis</div>
          <div className="summaryCell__value">{diagnosis}</div>
        </div>
        <div className="summaryCell">
          <div className="summaryCell__label">Treatment</div>
          <div className="summaryCell__value">{prescription}</div>
        </div>
        <div className="summaryCell">
          <div className="summaryCell__label">Safety</div>
          <div className="summaryCell__value">{safety}</div>
        </div>
        <div className="summaryCell">
          <div className="summaryCell__label">Approval</div>
          <div className="summaryCell__value">{approval}</div>
        </div>
        <div className="summaryCell">
          <div className="summaryCell__label">Outcome</div>
          <div className="summaryCell__value">
            {recovered} recovered{demoMode ? ' (simulated)' : ''}
          </div>
        </div>
      </div>
      <p
        style={{
          fontSize: 12,
          color: 'var(--text-faint)',
          marginTop: 14,
          marginBottom: 0,
        }}
      >
        AI reasons → policy constrains → human approves → Razorpay acts → system measures.
      </p>
    </Section>
  )
}