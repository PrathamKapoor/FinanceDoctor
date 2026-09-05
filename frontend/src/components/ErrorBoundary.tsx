import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  failed: boolean
  message: string | null
}

/** Minimal render-crash guard: never a blank white screen for case content. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, message: null }

  static getDerivedStateFromError(error: unknown): State {
    return {
      failed: true,
      message: error instanceof Error ? error.message : String(error),
    }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="state state--error" role="alert" style={{ padding: '24px 16px' }}>
        <p>Unexpected error</p>
        <p className="mono" style={{ fontSize: 12 }}>
          Something went wrong rendering this view. Your case data is unaffected —
          start a new case or reload the page.
        </p>
        {this.state.message ? (
          <p className="mono" style={{ fontSize: 12 }}>
            {this.state.message}
          </p>
        ) : null}
        <button className="btn btn--outline" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
