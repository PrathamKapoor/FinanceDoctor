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
      <div className="dxFeature">
        <div className="dxFeature__eyebrow">Leading diagnosis</div>
        <div className="dxFeature__value">
          {diagnosis.leading_hypothesis.replaceAll('_', ' ')}
        </div>
        <div className="dxFeature__row">
          <DiagnosisStat label="Confidence" value={conf.label} tone={conf.tone} light />
          <DiagnosisStat
            label="Recommended action"
            value={diagnosis.recommended_action_type.replaceAll('_', ' ')}
            mono
            light
          />
        </div>
        <p className="dxFeature__note">
          Model-assessed confidence — the model&apos;s own assessment, not a
          calibrated statistical probability.
        </p>
      </div>

      <p style={{ fontSize: 14, color: 'var(--text)', margin: '0 0 16px', maxWidth: 'var(--measure)' }}>{diagnosis.summary}</p>

      <KeyEvidence
        supporting={diagnosis.supporting_evidence_ids}
        contradicting={diagnosis.contradicting_evidence_ids}
      />

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
  light,
}: {
  label: string
  value: string
  tone?: 'success' | 'info' | 'muted'
  strong?: boolean
  mono?: boolean
  light?: boolean
}) {
  const valueColor = light
    ? tone === 'success'
      ? '#86efac'
      : tone === 'info'
        ? '#5eead4'
        : '#f1f5f9'
    : tone === 'success'
      ? 'var(--success)'
      : tone === 'info'
        ? 'var(--accent)'
        : 'var(--text)'
  return (
    <div>
      <div className="stat__label" style={light ? { color: '#94a3b8' } : undefined}>
        {label}
      </div>
      <div
        style={{
          fontSize: strong ? 20 : 16,
          fontWeight: strong ? 700 : 600,
          marginTop: 3,
          color: valueColor,
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

function shortEvidenceLabel(id: string): string {
  const parts = id.split('.')
  if (parts.length >= 3) {
    return `${parts[1]} · ${parts.slice(2).join(' ').replaceAll('_', ' ')}`
  }
  if (parts.length === 2) {
    return `${parts[0]} · ${parts[1].replaceAll('_', ' ')}`
  }
  return id.replaceAll('_', ' ')
}

function KeyEvidence({
  supporting,
  contradicting,
}: {
  supporting: string[]
  contradicting: string[]
}) {
  if (!supporting.length && !contradicting.length) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="card__kicker" style={{ marginBottom: 8 }}>
        Key supporting evidence
      </div>
      <div className="worker__meta" style={{ marginTop: 0 }}>
        {supporting.map((id) => (
          <span className="tag tag--support" key={id} title={id}>
            ✓ {shortEvidenceLabel(id)}
          </span>
        ))}
        {contradicting.map((id) => (
          <span className="tag tag--contradict" key={id} title={id}>
            ⚠ {shortEvidenceLabel(id)} challenged
          </span>
        ))}
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8, marginBottom: 0 }}>
        Full deterministic records with baseline / current values are listed below.
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