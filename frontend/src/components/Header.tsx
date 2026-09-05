export interface ProviderModes {
  razorpayMode?: string
  speechProvider?: string
  consultation?: string
}

function modeLabel(value: string | undefined, live: string, stub: string): string {
  return value === 'live' || value === 'minimax' ? live : stub
}

/** Provider badges reflect the live /health response — only true statuses shown. */
export function Header({ providers }: { providers?: ProviderModes }) {
  const razorpay = modeLabel(providers?.razorpayMode, 'Razorpay: Live API', 'Razorpay: Stub')
  const speech = modeLabel(providers?.speechProvider, 'Speech: Live MiniMax', 'Speech: Stub')
  const ai = modeLabel(providers?.consultation, 'AI: Live MiniMax', 'AI: Stub')
  const allStub =
    (providers?.razorpayMode ?? 'stub') === 'stub' &&
    (providers?.speechProvider ?? 'stub') === 'stub' &&
    (providers?.consultation ?? 'stub') === 'stub'
  return (
    <header className="app-header">
      <div className="app-header--inner">
        <div className="app-header__brand">
          <div className="app-header__mark" aria-hidden="true">
            +
          </div>
          <div>
            <div className="app-header__title">Financial Doctor</div>
            <div className="app-header__subtitle">
              Evidence-backed financial anomaly diagnosis &amp; bounded intervention
            </div>
          </div>
        </div>
        <div className="app-header__env">
          <span className="badge badge--muted" title="Razorpay provider mode (from backend health)">
            {razorpay}
          </span>
          <span className="badge badge--muted" title="Consultation model mode (from backend health)">
            {ai}
          </span>
          <span className="badge badge--muted" title="Speech provider mode (from backend health)">
            {speech}
          </span>
          <span
            className="badge badge--demo"
            title={
              allStub
                ? 'Demo environment — deterministic seeded incident, simulated payment provider'
                : 'Integration mode — one or more live providers active'
            }
          >
            {allStub ? 'Demo environment' : 'Integration mode'}
          </span>
        </div>
      </div>
    </header>
  )
}