import type { ReactNode } from 'react'

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'danger' | 'ok' | 'neutral'
}) {
  const valueClass =
    tone === 'danger'
      ? 'stat__value stat__delta--up'
      : tone === 'ok'
        ? 'stat__value stat__delta--down'
        : 'stat__value'
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className={valueClass}>{value}</div>
      {hint ? <div className="stat__hint">{hint}</div> : null}
    </div>
  )
}