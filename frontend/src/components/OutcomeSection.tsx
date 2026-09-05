import type { OutcomeView } from '../api/types'
import { formatCount, formatRatio, formatRupees } from '../lib/format'
import { Section } from './Section'
import { Stat } from './Stat'
import { StatusBadge } from './StatusBadge'
import { outcomeTone } from '../lib/status'

export function OutcomeSection({
  outcome,
  canSimulate,
  busy,
  onSimulate,
  demoMode = true,
}: {
  outcome: OutcomeView
  canSimulate: boolean
  busy: boolean
  onSimulate: () => void
  demoMode?: boolean
}) {
  const eff = outcome.effectiveness
  return (
    <Section
      kicker="Stage 5 — measured outcome"
      title="Treatment outcome"
      step={8}
      status={outcome.status}
      statusTone={outcomeTone(outcome.status)}
    >
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        {demoMode ? <StatusBadge tone="demo">Demo simulation</StatusBadge> : null}
        {outcome.finalized ? (
          <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>finalized</span>
        ) : (
          <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>observing provider events</span>
        )}
      </div>
      {demoMode ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 16px' }}>
          Recovery outcome simulated from the verified case model — Demo Mode,
          no real money moved.
        </p>
      ) : null}

      <div className="statGrid statGrid--3" style={{ marginBottom: 16 }}>
        <Stat
          label="Recovered revenue"
          value={formatRupees(outcome.amount_recovered_minor)}
          tone="ok"
          hint={`of ${formatRupees(outcome.amount_targeted_minor)} targeted`}
        />
        <Stat
          label="Recovery rate"
          value={formatRatio(outcome.conversion_rate)}
          hint={`${eff.targets_recovered} of ${eff.targets_total} targets`}
        />
        <Stat
          label="Targets pending"
          value={formatCount(outcome.targets_pending)}
          hint={`${formatCount(outcome.targets_failed + outcome.targets_expired)} unrecovered`}
        />
      </div>

      <div className="card__kicker" style={{ marginBottom: 8 }}>
        Per-target breakdown
      </div>
      <div className="statGrid statGrid--4">
        <Stat label="Recovered" value={formatCount(outcome.targets_succeeded)} tone="ok" />
        <Stat label="Pending targets" value={formatCount(outcome.targets_pending)} />
        <Stat label="Unrecovered" value={formatCount(outcome.targets_failed + outcome.targets_expired)} tone="danger" />
        <Stat label="Expired links" value={formatCount(outcome.targets_expired)} />
      </div>

      {canSimulate ? (
        <div style={{ marginTop: 20 }}>
          <button className="btn btn--outline" onClick={onSimulate} disabled={busy}>
            {busy ? 'Simulating webhook…' : 'Simulate provider webhook (payment_link.paid)'}
          </button>
          <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>
            Demo only: dispatches a signed <span className="mono">payment_link.paid</span> webhook
            through the verified boundary to advance the outcome deterministically.
          </p>
        </div>
      ) : null}
    </Section>
  )
}