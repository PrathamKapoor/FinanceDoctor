import type { TimelineEntry } from '../api/types'
import { Section } from './Section'

const STAGE_LABELS: Record<string, string> = {
  symptom: 'Symptom detected',
  investigation: 'Investigation',
  diagnosis: 'Diagnosis',
  prescription: 'Prescription',
  safety_check: 'Safety check',
  approval: 'Human approval',
  treatment: 'Treatment',
  outcome: 'Ongoing follow-up',
}

export function CaseTimeline({ timeline }: { timeline: TimelineEntry[] }) {
  return (
    <Section kicker="Deterministic case record" title="Financial Doctor case timeline" status="recorded" statusTone="muted">
      <div className="timeline">
        {timeline.map((entry, i) => {
          const last = i === timeline.length - 1
          const pending = entry.status === 'PENDING'
          const label = STAGE_LABELS[entry.stage] ?? entry.stage
          const time = entry.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString('en-IN', {
                hour: '2-digit',
                minute: '2-digit',
              })
            : '—'
          return (
            <div
              className={`timeline__item${pending ? ' timeline__item--pending' : ''}`}
              key={`${entry.stage}-${i}`}
            >
              <div className="timeline__time">{time}</div>
              <div className="timeline__rail">
                <div className="timeline__dot" />
                {!last ? <div className="timeline__line" /> : null}
              </div>
              <div className="timeline__body">
                <div className="timeline__stage">{label}</div>
                {entry.note ? (
                  <div className="timeline__note">{entry.note}</div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </Section>
  )
}