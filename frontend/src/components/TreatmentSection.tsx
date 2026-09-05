import type { TreatmentView } from '../api/types'
import { formatDateTime, formatCount } from '../lib/format'
import { Section } from './Section'
import { StatusBadge } from './StatusBadge'
import { executionTone } from '../lib/status'

export function TreatmentSection({
  treatment,
  demoMode = true,
}: {
  treatment: TreatmentView
  demoMode?: boolean
}) {
  const steps = [
    { label: 'Validating approval', done: true },
    { label: 'Verifying action hash', done: true },
    { label: 'Checking policy', done: true },
    {
      label: demoMode ? 'Creating Payment Link (simulated)' : 'Creating Payment Link',
      done: treatment.status === 'SUCCEEDED',
    },
    { label: 'Recording execution', done: treatment.status === 'SUCCEEDED' },
  ]
  return (
    <Section
      kicker="Stage 4 / 5 — controlled execution"
      title="Treatment"
      step={7}
      status={treatment.status}
      statusTone={executionTone(treatment.status)}
    >
      {demoMode ? (
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <StatusBadge tone="demo">Demo simulation</StatusBadge>
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            Payment Link recovery action simulated — Razorpay-compatible demo
            provider, no real transaction.
          </span>
        </div>
      ) : null}
      <div className="statGrid statGrid--4" style={{ marginBottom: 16 }}>
        <div className="stat">
          <div className="stat__label">Payment Links created</div>
          <div className="stat__value">{formatCount(treatment.links_count)}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Provider operation</div>
          <div className="stat__value" style={{ fontSize: 15 }}>
            {treatment.provider_operation?.replaceAll('_', ' ') ?? '—'}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Executed at</div>
          <div className="stat__value" style={{ fontSize: 14 }}>
            {formatDateTime(treatment.completed_at ?? treatment.started_at)}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">Provider reference</div>
          <div className="stat__value mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>
            {treatment.provider_reference ?? '—'}
          </div>
        </div>
      </div>

      <div className="card__kicker" style={{ marginBottom: 8 }}>
        Execution sequence
      </div>
      <div className="policyList policyList--rail">
        {steps.map((s) => (
          <div className="policyCheck policyCheck--pass" key={s.label}>
            <span className="policyCheck__icon" aria-hidden="true">
              {s.done ? '✓' : '•'}
            </span>
            <div className="policyCheck__title">{s.label}</div>
          </div>
        ))}
      </div>

      {treatment.status === 'FAILED' ? (
        <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 12 }}>
          {treatment.error_code ? `${treatment.error_code}: ` : ''}
          {treatment.error_message ?? 'Treatment execution failed.'}
        </p>
      ) : null}
    </Section>
  )
}