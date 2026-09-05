import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import type { CaseView } from './api/types'
import { Header } from './components/Header'
import { JourneyStepper } from './components/JourneyStepper'
import { SymptomCard, SymptomSection } from './components/SymptomSection'
import { InvestigationSection } from './components/InvestigationSection'
import { DiagnosisSection } from './components/DiagnosisSection'
import { PrescriptionSection } from './components/PrescriptionSection'
import { SafetySection } from './components/SafetySection'
import { ApprovalSection } from './components/ApprovalSection'
import { TreatmentSection } from './components/TreatmentSection'
import { OutcomeSection } from './components/OutcomeSection'
import { CaseTimeline } from './components/CaseTimeline'
import { CaseSummary } from './components/CaseSummary'
import { ConsultPanel } from './components/ConsultPanel'
import { ErrorBoundary } from './components/ErrorBoundary'
import type { ProviderModes } from './components/Header'

type LoadingState = 'starting' | 'acting' | null

export function App() {
  const [data, setData] = useState<CaseView | null>(null)
  const [loading, setLoading] = useState<LoadingState>('starting')
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [providers, setProviders] = useState<ProviderModes | undefined>(undefined)
  const startedRef = useRef(false)

  const load = useCallback(async () => {
    setLoading('starting')
    setError(null)
    setActionError(null)
    try {
      const [health, next] = await Promise.all([api.getHealth(), api.startCase()])
      setProviders({
        razorpayMode: health.razorpay_mode,
        speechProvider: health.speech_provider,
        consultation: health.consultation,
      })
      setData(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(null)
    }
  }, [])

  useEffect(() => {
    // Guard against React StrictMode double-invoking effects in development:
    // start exactly one demo case on mount.
    if (startedRef.current) return
    startedRef.current = true
    void load()
  }, [load])

  const run = useCallback(async (task: () => Promise<CaseView>) => {
    setLoading('acting')
    setActionError(null)
    try {
      setData(await task())
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(null)
    }
  }, [])

  const approve = useCallback(() => {
    if (!data) return
    void run(() => api.approve(data.case_id, 'human_reviewer', 'Treatment approved'))
  }, [data, run])

  const reject = useCallback(() => {
    if (!data) return
    void run(() => api.reject(data.case_id, 'human_reviewer', 'Rejected'))
  }, [data, run])

  const execute = useCallback(() => {
    if (!data) return
    void run(() => api.execute(data.case_id))
  }, [data, run])

  const simulate = useCallback(() => {
    if (!data) return
    void run(() => api.simulate(data.case_id))
  }, [data, run])

  const runFullDemo = useCallback(async () => {
    if (!data) return
    setLoading('acting')
    setActionError(null)
    try {
      let next = await api.approve(data.case_id, 'demo_operator', 'Approved for demo')
      next = await api.execute(data.case_id)
      next = await api.simulate(data.case_id)
      setData(next)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(null)
    }
  }, [data])

  if (loading === 'starting' && !data) {
    return (
      <>
        <Header providers={providers} />
        <main className="main">
          <div className="state">
            <div className="loadingRow">
              <span className="spinner" role="status" aria-label="Loading financial evidence" />
              Loading financial evidence
            </div>
          </div>
        </main>
      </>
    )
  }

  if (error && !data) {
    return (
      <>
        <Header providers={providers} />
        <main className="main">
          <div className="state state--error" role="alert">
            <p>Backend unavailable</p>
            <p className="mono" style={{ fontSize: 13 }}>
              {error}
            </p>
            <button className="btn btn--outline" onClick={() => void load()}>
              Retry
            </button>
          </div>
        </main>
      </>
    )
  }

  if (!data) return null

  const approvalPending = data.approval?.status === 'PENDING'
  const approved = data.approval?.status === 'APPROVED'
  const awaitingExecute = approved && !data.treatment
  const awaitingOutcome = data.outcome != null && !data.outcome.finalized
  // Demo-explicit: only a backend-confirmed live mode lifts simulation labeling.
  const demoMode = providers?.razorpayMode !== 'live'

  return (
    <>
      <Header providers={providers} />
      <main className="main">
        <JourneyStepper stages={data.stages} />

        <div className="content">
          <ErrorBoundary>
          {actionError ? (
            <div className="state state--error" role="alert" style={{ padding: '12px 16px', textAlign: 'left' }}>
              {actionError}
            </div>
          ) : null}

          {data.symptom ? (
            <div id="section-symptom">
              <SymptomSection symptom={data.symptom} />
            </div>
          ) : null}
          {data.symptom ? (
            <div id="section-health">
              <SymptomCard symptom={data.symptom} health={data.health} />
            </div>
          ) : null}
          {data.investigation ? (
            <div id="section-investigation">
              <InvestigationSection investigation={data.investigation} />
            </div>
          ) : null}
          {data.diagnosis ? (
            <div id="section-diagnosis">
              <DiagnosisSection diagnosis={data.diagnosis} />
            </div>
          ) : null}
          {data.prescription ? (
            <div id="section-prescription">
              <PrescriptionSection prescription={data.prescription} />
            </div>
          ) : null}
          {data.policy ? (
            <div id="section-safety">
              <SafetySection policy={data.policy} />
            </div>
          ) : null}

          {data.approval ? (
            <div id="section-approval">
              <ApprovalSection
                approval={data.approval}
                busy={loading === 'acting'}
                error={actionError}
                onApprove={approve}
                onReject={reject}
              />
            </div>
          ) : null}

          {awaitingExecute ? (
            <div className="card">
              <div className="card__body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div className="card__kicker">Treatment authorized</div>
                  <div style={{ fontWeight: 600 }}>Ready to execute the approved recovery action</div>
                  <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
                    The immutable action snapshot is verified before any Razorpay operation runs.
                  </p>
                </div>
                <button className="btn btn--primary" onClick={execute} disabled={loading === 'acting'}>
                  {loading === 'acting' ? 'Executing…' : 'Execute treatment'}
                </button>
              </div>
            </div>
          ) : null}

          {data.treatment ? (
            <div id="section-treatment">
              <TreatmentSection treatment={data.treatment} demoMode={demoMode} />
            </div>
          ) : null}

          {data.outcome ? (
            <div id="section-outcome">
              <OutcomeSection
                outcome={data.outcome}
                canSimulate={awaitingOutcome}
                busy={loading === 'acting'}
                onSimulate={simulate}
                demoMode={demoMode}
              />
            </div>
          ) : null}

          <ConsultPanel caseId={data.case_id} />

          {data.timeline.length ? <CaseTimeline timeline={data.timeline} /> : null}

          {data.outcome ? <CaseSummary data={data} demoMode={demoMode} /> : null}

          <div className="card">
            <div className="card__body" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              {approvalPending ? (
                <button className="btn btn--ghost" onClick={() => void runFullDemo()} disabled={loading === 'acting'}>
                  ▶ Run full demo (approve → execute → simulate)
                </button>
              ) : null}
              <button className="btn btn--ghost" onClick={() => void load()} disabled={loading === 'acting'}>
                ↺ New case
              </button>
              <span className="mono" style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                case {data.case_id}
              </span>
            </div>
          </div>
          </ErrorBoundary>
        </div>
      </main>
    </>
  )
}