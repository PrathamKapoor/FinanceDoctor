import type { PrescriptionView } from '../api/types'
import { formatCount, formatRupees } from '../lib/format'
import { Section } from './Section'
import { Stat } from './Stat'

export function PrescriptionSection({ prescription }: { prescription: PrescriptionView }) {
  return (
    <Section
      kicker="Stage 4 — recommended treatment"
      title="Prescription"
      step={4}
      status={prescription.status}
      statusTone="info"
    >
      <div className="statGrid statGrid--4" style={{ marginBottom: 16 }}>
        <Stat label="Recommended action" value={prescription.action_type.replaceAll('_', ' ')} />
        <Stat label="Eligible targets" value={formatCount(prescription.targets_count)} />
        <Stat label="Total eligible amount" value={formatRupees(prescription.total_amount_minor)} />
        <Stat label="Currency" value={prescription.currency} />
      </div>
      <p style={{ color: 'var(--text-muted)', fontSize: 14, margin: 0 }}>
        {prescription.rationale}
      </p>
      <div style={{ marginTop: 16 }}>
        <div className="card__kicker" style={{ marginBottom: 8 }}>
          Deterministic recovery targets (backend-controlled)
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data">
            <thead>
              <tr>
                <th>Payment</th>
                <th>Method</th>
                <th>Failure reason</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {prescription.targets.slice(0, 20).map((t) => (
                <tr key={t.payment_id}>
                  <td className="mono">{t.payment_id}</td>
                  <td>{t.payment_method}</td>
                  <td className="mono">{t.failure_reason}</td>
                  <td className="mono">{formatRupees(t.amount_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {prescription.targets.length > 20 ? (
          <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>
            …and {formatCount(prescription.targets.length - 20)} more targets. Amounts, customer
            IDs, and provider operations remain backend-controlled and cannot be modified here.
          </p>
        ) : null}
      </div>
    </Section>
  )
}