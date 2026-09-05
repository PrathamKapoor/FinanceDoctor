import { describe, expect, it } from 'vitest'
import { formatRupees, formatRatio, formatDelta, formatMultiplier } from './format'

describe('formatRupees', () => {
  it('converts integer minor units to a whole-rupee currency string', () => {
    expect(formatRupees(8700000)).toContain('87,000')
    expect(formatRupees(0)).toContain('0')
    expect(formatRupees(50000)).toContain('500')
  })
})

describe('formatRatio', () => {
  it('turns a ratio into a percentage string', () => {
    expect(formatRatio(0.3824)).toBe('38.24%')
    expect(formatRatio(0.0454)).toBe('4.54%')
  })
  it('renders a dash for null', () => {
    expect(formatRatio(null)).toBe('—')
  })
})

describe('formatDelta / formatMultiplier', () => {
  it('adds a sign and fixed precision', () => {
    expect(formatDelta(0.3488)).toBe('+0.35')
    expect(formatMultiplier(3.79)).toBe('3.79×')
  })
})