import type { Symptom, HealthView } from '../api/types'
import { formatCount, formatMultiplier, formatRatio, formatDateTime } from '../lib/format'
import { Section } from './Section'
import { Stat } from './Stat'
import { HealthChart } from './HealthChart'

export function SymptomSection({ symptom }: { symptom: Symptom }) {
  const a = symptom.anomaly
  return (
    <div className="hero" aria-label={symptom.title}>
      <span className="hero__alert">⚠ Anomaly detected</span>
      <h1 className="hero__title">{symptom.title}</h1>
      <p className="hero__subtitle">
        {symptom.incident_type} · detected within {formatDateTime(symptom.start_time)} →{' '}
        {formatDateTime(symptom.end_time)}
      </p>

      <div className="hero__metrics">
        <div className="heroMetric">
          <div className="heroMetric__label">Baseline failure rate</div>
          <div className="heroMetric__value">{formatRatio(a.baseline)}</div>
          <div className="heroMetric__hint">30-day healthy baseline</div>
        </div>
        <div className="heroMetric">
          <div className="heroMetric__label">Current failure rate</div>
          <div className="heroMetric__value heroMetric__value--danger">
            {formatRatio(a.current)}
          </div>
          <div className="heroMetric__hint">{formatCount(a.sample_size)} attempts</div>
        </div>
        <div className="heroMetric">
          <div className="heroMetric__label">Increase</div>
          <div className="heroMetric__value heroMetric__value--danger">
            {formatMultiplier(a.relative_delta)}
          </div>
          <div className="heroMetric__hint">vs. baseline</div>
        </div>
        <div className="heroMetric">
          <div className="heroMetric__label">Anomaly score (z)</div>
          <div className="heroMetric__value heroMetric__value--danger">
            {a.anomaly_score.toFixed(3)}
          </div>
          <div className="heroMetric__hint">threshold {a.threshold.toFixed(1)}</div>
        </div>
      </div>
    </div>
  )
}

export function SymptomCard({
  symptom,
  health,
}: {
  symptom: Symptom
  health?: HealthView
}) {
  return (
    <Section kicker="Stage 1 — deterministic detection" title="Symptom / incident summary" step={1} status="detected" statusTone="danger">
      <div className="statGrid statGrid--4" style={{ marginBottom: 16 }}>
        <Stat label="Incident type" value="Payment method failure spike" />
        <Stat label="Affected method" value={symptom.affected_value ?? '—'} tone="danger" />
        <Stat label="Detection window" value={formatDateTime(symptom.start_time)} />
        <Stat
          label="Current vs baseline"
          value={`${formatRatio(symptom.overall.current.failure_rate)} vs ${formatRatio(
            symptom.overall.baseline.failure_rate,
          )}`}
          tone="danger"
        />
      </div>
      {health ? <HealthChart health={health} /> : null}
    </Section>
  )
}