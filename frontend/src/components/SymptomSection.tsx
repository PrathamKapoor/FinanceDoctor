import type { Symptom, HealthView } from '../api/types'
import { formatCount, formatMultiplier, formatRatio, formatDateTime } from '../lib/format'
import { Section } from './Section'
import { Stat } from './Stat'
import { HealthChart } from './HealthChart'

export function SymptomSection({ symptom }: { symptom: Symptom }) {
  const a = symptom.anomaly
  const baseline = a.baseline
  const current = a.current
  const scaleMax = Math.max(current * 1.12, baseline * 1.5, 0.01)
  const basePos = Math.min(100, (baseline / scaleMax) * 100)
  const curPos = Math.min(100, (current / scaleMax) * 100)
  return (
    <div className="hero" aria-label={symptom.title}>
      <div className="hero__top">
        <span className="hero__alert">⚠ Anomaly detected</span>
        <span className="hero__incident">{symptom.incident_type.replaceAll('_', ' ')}</span>
      </div>
      <h1 className="hero__title">{symptom.title}</h1>
      <p className="hero__subtitle">
        {symptom.incident_type} · detected within {formatDateTime(symptom.start_time)} →{' '}
        {formatDateTime(symptom.end_time)}
      </p>

      <div className="hero__dominant">
        <div className="hero__currentWrap">
          <div className="hero__currentLabel">Current failure rate</div>
          <div className="hero__currentValue">{formatRatio(current)}</div>
          <div className="hero__scale" aria-hidden="true">
            <div className="hero__scaleTrack">
              <span className="hero__scaleBase" style={{ left: `${basePos}%` }} />
              <span className="hero__scaleCur" style={{ left: `${curPos}%` }} />
            </div>
            <div className="hero__scaleCaption">
              <span>Baseline</span>
              <span>Current window</span>
            </div>
          </div>
        </div>
        <div className="hero__side">
          <div className="heroMini">
            <div className="heroMini__label">Baseline failure rate</div>
            <div className="heroMini__value">{formatRatio(baseline)}</div>
            <div className="heroMini__hint">30-day healthy baseline</div>
          </div>
          <div className="heroMini">
            <div className="heroMini__label">Increase</div>
            <div className="heroMini__value heroMetric__value--danger">
              {formatMultiplier(a.relative_delta)}
            </div>
            <div className="heroMini__hint">
              vs. baseline (+{(a.absolute_delta * 100).toFixed(2)}pp)
            </div>
          </div>
          <div className="heroMini">
            <div className="heroMini__label">Anomaly score (z)</div>
            <div className="heroMini__value heroMetric__value--danger">
              {a.anomaly_score.toFixed(3)}
            </div>
            <div className="heroMini__hint">
              threshold {a.threshold.toFixed(1)} · {formatCount(a.sample_size)} attempts
            </div>
          </div>
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