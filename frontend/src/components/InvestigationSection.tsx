import type { InvestigationView } from '../api/types'
import { formatRatio } from '../lib/format'
import { Section } from './Section'

const WORKER_TITLES: Record<string, { title: string; short: string }> = {
  temporal: { title: 'Temporal analysis', short: 'Time-of-day / day-of-week' },
  payment_method: { title: 'Payment method analysis', short: 'Per-method failure profile' },
  cohort: { title: 'Customer cohort analysis', short: 'New vs. returning customers' },
  failure_reason: { title: 'Failure reason analysis', short: 'Error-code distribution' },
}

export function InvestigationSection({ investigation }: { investigation: InvestigationView }) {
  return (
    <Section
      kicker="Stage 3 — M2.7 investigation workers"
      title="Investigation"
      step={2}
      status={investigation.state}
      statusTone="success"
    >
      <p style={{ margin: '0 0 16px', color: 'var(--text-muted)', fontSize: 14 }}>
        Four specialized workers reasoned over pre-computed deterministic evidence, each along
        one dimension. Workers never calculate financial metrics — they interpret and cite them.
      </p>
      <div className="workers">
        {investigation.workers.map((w, idx) => {
          const meta = WORKER_TITLES[w.worker] ?? { title: w.worker, short: '' }
          const errored = Boolean(w.error)
          const unitNo = `W-0${idx + 1}`
          return (
            <div className="worker" key={w.worker}>
              <div className="worker__top">
                <span className="worker__index" aria-hidden="true">{unitNo}</span>
                <span
                  className={`worker__state ${errored ? 'worker__state--error' : 'worker__state--done'}`}
                >
                  {errored ? '✕ Needs attention' : '✓ Analysis complete'}
                </span>
              </div>
              <div className="worker__name">{meta.title}</div>
              <div className="card__kicker">{meta.short}</div>
              <p className="worker__finding">
                {errored ? w.error : w.finding}
              </p>
              <div className="worker__meta">
                <span className="tag">confidence {formatRatio(w.confidence, 0)}</span>
                <span className="tag">cites {w.evidence_ids.length} evidence</span>
                {w.supports.map((h) => (
                  <span className="tag tag--support" key={`s-${h}`}>
                    + {h.replaceAll('_', ' ')}
                  </span>
                ))}
                {w.contradicts.map((h) => (
                  <span className="tag tag--contradict" key={`c-${h}`}>
                    − {h.replaceAll('_', ' ')}
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </Section>
  )
}