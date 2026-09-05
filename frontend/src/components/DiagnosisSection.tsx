import { useState } from 'react'
import type { DiagnosisView, EvidenceItem } from '../api/types'
import { formatRatio } from '../lib/format'
import { Section } from './Section'

// Confidence is model-assessed — not a calibrated statistical probability.
// The UI labels it exactly as the backend contract does.
function confidenceLabel(confidence: number): { label: string; tone: 'success' | 'info' | 'muted' } {
  if (confidence >= 0.75) return { label: 'High confidence', tone: 'success' }
  if (confidence >= 0.5) return { label: 'Moderate confidence', tone: 'info' }
  return { label: 'Low confidence', tone: 'muted' }
}

export function DiagnosisSection({ diagnosis }: { diagnosis: DiagnosisView }) {
  const conf = confidenceLabel(diagnosis.confidence)
  return (
    <Section
      kicker="Stage 3 — M3 senior diagnosis"
      title="Diagnosis"
      step={3}
      status="complete"
      statusTone="success"
    >
      <div className="statGrid statGrid--3" style={{ marginBottom: 16 }}>
        <DiagnosisStat
          label="Leading diagnosis"
          value={diagnosis.leading_hypothesis.replaceAll('_', ' ')}
          strong
        />
        <DiagnosisStat label="Confidence" value={conf.label} tone={conf.tone} />
        <DiagnosisStat
          label="Recommended action"
          value={diagnosis.recommended_action_type.replaceAll('_', ' ')}
          mono
        />
      </div>

      <p style={{ fontSize: 14, color: 'var(--text)', margin: '0 0 16px' }}>{diagnosis.summary}</p>

      <EvidenceExplorer evidence={diagnosis.evidence} />

      <Differential hypotheses={diagnosis.alternative_hypotheses} leading={diagnosis.leading_hypothesis} />

      {diagnosis.uncertainties.length ? (
        <details className="details">
          <summary>Uncertainties &amp; limitations</summary>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text-muted)', fontSize: 13 }}>
            {diagnosis.uncertainties.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </Section>
  )
}

function DiagnosisStat({
  label,
  value,
  tone,
  strong,
  mono,
}: {
  label: string
  value: string
  tone?: 'success' | 'info' | 'muted'
  strong?: boolean
  mono?: boolean
}) {
  return (
    <div>
      <div className="stat__label">{label}</div>
      <div
        style={{
          fontSize: strong ? 20 : 16,
          fontWeight: strong ? 700 : 600,
          marginTop: 3,
          color: tone === 'success' ? 'var(--success)' : tone === 'info' ? 'var(--accent)' : 'var(--text)',
          fontFamily: mono ? 'var(--font-mono)' : undefined,
        }}
      >
        {value}
      </div>
    </div>
  )
}

function Differential({
  hypotheses,
  leading,
}: {
  hypotheses: DiagnosisView['alternative_hypotheses']
  leading: string
}) {
  if (!hypotheses.length) return null
  const leadingScore = 1
  const rows = [
    { hypothesis: leading, score: leadingScore, reason: 'Leading hypothesis' },
    ...hypotheses,
  ]
  return (
    <div style={{ marginTop: 20 }}>
      <div className="card__kicker" style={{ marginBottom: 8 }}>
        Differential diagnosis
      </div>
      <div className="bars">
        {rows.map((h) => (
          <div className="barRow" key={h.hypothesis}>
            <span className="barRow__label">{h.hypothesis.replaceAll('_', ' ')}</span>
            <div className="barRow__track">
              <div
                className={h.hypothesis === leading ? 'barRow__fill barRow__fill--warn' : 'barRow__fill'}
                style={{ width: `${Math.min(100, h.score * 100)}%` }}
              />
            </div>
            <span className="barRow__value">{formatRatio(h.score, 0)}</span>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>
        Relative evidence weighting considered by M3 before selecting the leading hypothesis.
        Scores are model-assessed, not statistical probabilities.
      </p>
    </div>
  )
}

function EvidenceExplorer({ evidence }: { evidence: EvidenceItem[] }) {
  const [open, setOpen] = useState(false)
  if (!evidence.length) return null
  return (
    <details className="details" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Evidence explorer ({evidence.length} deterministic items)</summary>
      <div style={{ overflowX: 'auto' }}>
        <table className="data">
          <thead>
            <tr>
              <th>Evidence ID</th>
              <th>Domain</th>
              <th>Metric / value</th>
              <th>Baseline</th>
              <th>Current</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((e) => (
              <tr key={e.id}>
                <td className="mono">{e.id}</td>
                <td>{e.dimension ?? e.kind}</td>
                <td className="mono">{String(e.value)}</td>
                <td className="mono">{e.baseline === null ? '—' : String(e.baseline)}</td>
                <td className="mono">{e.current === null ? '—' : String(e.current)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}