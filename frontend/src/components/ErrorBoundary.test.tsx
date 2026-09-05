import { describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

function Boom(): ReactElement {
  throw new Error('render crash')
}

describe('ErrorBoundary', () => {
  it('renders a safe fallback instead of a blank screen', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Unexpected error')).toBeInTheDocument()
    expect(screen.getByText(/Your case data is unaffected/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it('renders children when nothing crashes', () => {
    render(
      <ErrorBoundary>
        <div>healthy content</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('healthy content')).toBeInTheDocument()
  })
})
