import type { ReactNode } from 'react'
import type { Tone } from '../lib/status'

const TONE_CLASS: Record<Tone, string> = {
  danger: 'badge--danger',
  success: 'badge--success',
  info: 'badge--info',
  muted: 'badge--muted',
  demo: 'badge--demo',
}

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge ${TONE_CLASS[tone]}`}>{children}</span>
}