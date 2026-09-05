import type { ReactNode } from 'react'
import { StatusBadge } from './StatusBadge'
import { humanizeStatus } from '../lib/status'
import type { Tone } from '../lib/status'

export function Section({
  kicker,
  title,
  status,
  statusTone,
  step,
  children,
}: {
  kicker: string
  title: string
  status?: string | null
  statusTone?: Tone
  step?: number
  children: ReactNode
}) {
  return (
    <section className="card" aria-label={title}>
      <header className="card__header">
        <div>
          <div className="card__kicker">
            {step !== undefined ? `Step ${step} · ` : ''}
            {kicker}
          </div>
          <h2 className="card__title">{title}</h2>
        </div>
        {status ? (
          <StatusBadge tone={statusTone ?? 'muted'}>{humanizeStatus(status)}</StatusBadge>
        ) : null}
      </header>
      <div className="card__body">{children}</div>
    </section>
  )
}