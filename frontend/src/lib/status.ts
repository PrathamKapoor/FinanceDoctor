// Shared status tone + humanization helpers. Kept separate from
// components so react-refresh only-export-components stays clean.

export type Tone = 'danger' | 'success' | 'info' | 'muted' | 'demo'

export function outcomeTone(status: string): Tone {
  switch (status) {
    case 'RECOVERED':
      return 'success'
    case 'PARTIALLY_RECOVERED':
      return 'info'
    case 'PENDING':
      return 'muted'
    case 'NO_RECOVERY':
    case 'FAILED':
    case 'EXPIRED':
    default:
      return 'danger'
  }
}

export function approvalTone(status: string): Tone {
  switch (status) {
    case 'APPROVED':
      return 'success'
    case 'REJECTED':
      return 'danger'
    case 'EXPIRED':
      return 'danger'
    default:
      return 'muted'
  }
}

export function executionTone(status: string): Tone {
  switch (status) {
    case 'SUCCEEDED':
      return 'success'
    case 'EXECUTING':
      return 'info'
    case 'FAILED':
      return 'danger'
    default:
      return 'muted'
  }
}

export function humanizeStatus(status: string | null | undefined): string {
  if (!status) return 'Pending'
  return status
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}