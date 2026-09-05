// Display formatting helpers. Financial amounts from the backend are integer
// minor units (paise for INR). We only format for display — never recompute a
// financial quantity client-side beyond a safe minor→major conversion.

const rupeeFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

export function formatRupees(minorUnits: number): string {
  // INR minor units are paise; 100 paise = ₹1. The backend only ever produces
  // minor units that are exact multiples of 100 for INR, so dividing is safe.
  const whole = Math.round(minorUnits / 100)
  return rupeeFormatter.format(whole)
}

export function formatRatio(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value)
}

export function formatDelta(value: number, digits = 2): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}`
}

export function formatMultiplier(value: number, digits = 2): string {
  return `${value.toFixed(digits)}×`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}