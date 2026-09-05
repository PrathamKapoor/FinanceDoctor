import type { PolicyView } from '../api/types'
import { Section } from './Section'
import { StatusBadge } from './StatusBadge'

const CHECK_TITLES: Record<string, string> = {
  authorization: 'Action is allowlisted',
  merchant_configured: 'Merchant recovery workflow enabled',
  action_type_allowed: 'Action type in allowlist',
  amount_limit: 'Recovery amount within limit',
  target_count: 'Target count within limit',
  duplicate_prevention: 'No duplicate recovery actions',
  idempotency: 'Idempotency verified',
  eligibility: 'All targets are eligible',
  action_integrity: 'Action integrity verified',
  investigation_integrity: 'Investigation lineage valid',
  rate_limit: 'Rate limit respected',
  amount_per_target: 'Per-target amount within limit',
}

export function SafetySection({ policy }: { policy: PolicyView }) {
  const statusTone = policy.decision === 'REJECTED' ? 'danger' : 'success'
  const blocked = policy.decision === 'REJECTED' || policy.failed_checks.length > 0
  const passed = policy.checks.filter((c) => c.status === 'PASS').length
  const total = policy.checks.length
  return (
    <Section
      kicker="Stage 4 — deterministic policy engine"
      title="Safety & policy check"
      step={5}
      status={blocked ? 'rejected' : 'passed'}
      statusTone={statusTone}
    >
      <div className="policyStrip">
        <div className="policyStrip__left">
          <span className="policyStrip__kicker">Deterministic verdict</span>
          <span className="policyStrip__decision">
            {blocked ? 'Blocked by policy' : `${passed} / ${total} checks passed`}
          </span>
        </div>
        <span className="policyStrip__rule">
          AI recommends · system validates · human decides
        </span>
      </div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        <StatusBadge tone={blocked ? 'danger' : 'success'}>
          {blocked ? 'Blocked' : 'All checks passed'}
        </StatusBadge>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Decision: <strong>{policy.decision.replaceAll('_', ' ')}</strong>
        </span>
      </div>
      <div className="policyList policyList--grid">
        {policy.checks.map((c) => {
          const failed = c.status === 'FAIL'
          return (
            <div
              className={`policyCheck ${failed ? 'policyCheck--fail' : 'policyCheck--pass'}`}
              key={c.check}
            >
              <span className="policyCheck__icon" aria-hidden="true">
                {failed ? '✕' : '✓'}
              </span>
              <div>
                <div className="policyCheck__title">
                  {CHECK_TITLES[c.check] ?? c.check}
                  <span style={{ color: 'var(--text-faint)', fontSize: 11 }}> ({c.status})</span>
                </div>
                <div className="policyCheck__msg">{c.message}</div>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="card__kicker">Action snapshot hash (immutable)</div>
        <div className="mono" style={{ wordBreak: 'break-all', fontSize: 12, color: 'var(--text-muted)' }}>
          {policy.action_snapshot_hash}
        </div>
      </div>
    </Section>
  )
}