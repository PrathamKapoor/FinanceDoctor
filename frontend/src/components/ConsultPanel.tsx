import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { ConsultationResponse } from '../api/types'
import { Section } from './Section'

type ConsultStatus = 'ready' | 'thinking' | 'answer' | 'error'
type AudioStatus = 'none' | 'loading' | 'ready' | 'error'

const SECTION_ANCHORS: Record<string, string> = {
  incident: 'section-symptom',
  metrics: 'section-health',
  investigation: 'section-investigation',
  diagnosis: 'section-diagnosis',
  evidence: 'section-diagnosis',
  treatment: 'section-prescription',
  policy: 'section-safety',
  approval: 'section-approval',
  execution: 'section-treatment',
  outcome: 'section-outcome',
}

const EXAMPLE_QUESTIONS = [
  'Doctor, what happened to my payments?',
  'Why did the failure rate increase?',
  'Which payment method was affected?',
  'What treatment did you recommend?',
  'Did the treatment actually work?',
]

function scrollToSection(section: string) {
  const anchor = SECTION_ANCHORS[section]
  if (!anchor) return
  const el = document.getElementById(anchor)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  el.animate(
    [
      { boxShadow: '0 0 0 0 rgba(15, 118, 110, 0)' },
      { boxShadow: '0 0 0 3px rgba(15, 118, 110, 0.55)' },
      { boxShadow: '0 0 0 0 rgba(15, 118, 110, 0)' },
    ],
    { duration: 1200 },
  )
}

export function ConsultPanel({ caseId }: { caseId: string }) {
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState<ConsultStatus>('ready')
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<ConsultationResponse | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [audioStatus, setAudioStatus] = useState<AudioStatus>('none')
  const [audioError, setAudioError] = useState<string | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const ask = async (text: string) => {
    const q = text.trim()
    if (!q || status === 'thinking') return
    setStatus('thinking')
    setError(null)
    setResponse(null)
    setAudioUrl(null)
    setAudioStatus('none')
    setAudioError(null)
    try {
      const res = await api.consult(caseId, q)
      setResponse(res)
      setStatus('answer')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }

  const listen = async () => {
    if (!response || audioStatus === 'loading') return
    setAudioStatus('loading')
    setAudioError(null)
    try {
      const audio = await api.consultationAudio(caseId, response.consultation_id)
      setAudioUrl(`data:${audio.mime_type};base64,${audio.data_base64}`)
      setAudioStatus('ready')
    } catch (e) {
      setAudioError(e instanceof Error ? e.message : String(e))
      setAudioStatus('error')
    }
  }

  return (
    <Section
      kicker="Stage 7A — read-only consultation"
      title="Ask Financial Doctor"
      status={status === 'thinking' ? 'thinking' : status === 'error' ? 'error' : response ? 'answered' : 'ready'}
      statusTone={status === 'error' ? 'danger' : response ? 'success' : 'muted'}
    >
      <p style={{ margin: '0 0 12px', color: 'var(--text-muted)', fontSize: 14 }}>
        Based on the active financial case. The Doctor explains — it cannot approve,
        execute, or change anything.
      </p>

      <div className="consult__examples">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            className="btn btn--ghost consult__example"
            disabled={status === 'thinking'}
            onClick={() => {
              setQuestion(q)
              void ask(q)
            }}
          >
            {q}
          </button>
        ))}
      </div>

      <form
        className="consult__form"
        onSubmit={(e) => {
          e.preventDefault()
          void ask(question)
        }}
      >
        <label className="consult__label" htmlFor="consult-question">
          Your question (typed — voice input is not offered because no verified
          speech-to-text API exists)
        </label>
        <div className="consult__row">
          <input
            id="consult-question"
            className="consult__input"
            type="text"
            value={question}
            maxLength={1000}
            placeholder="Why did my payment success drop?"
            disabled={status === 'thinking'}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" className="btn btn--primary" disabled={status === 'thinking' || !question.trim()}>
            {status === 'thinking' ? 'Thinking…' : 'Ask Doctor'}
          </button>
        </div>
      </form>

      {status === 'thinking' ? (
        <div className="loadingRow" style={{ justifyContent: 'flex-start', marginTop: 12 }}>
          <span className="spinner" role="status" aria-label="Consulting the Financial Doctor" />
          Consulting the case evidence…
        </div>
      ) : null}

      {status === 'error' && error ? (
        <div className="state state--error" role="alert" style={{ padding: '12px 16px', textAlign: 'left', marginTop: 12 }}>
          Consultation temporarily unavailable. Your Financial Doctor case data remains available.
          <div className="mono" style={{ fontSize: 12, marginTop: 4 }}>{error}</div>
        </div>
      ) : null}

      {status === 'answer' && response ? (
        <div className="consult__answer">
          <div className="card__kicker">Financial Doctor</div>
          <p style={{ margin: '6px 0 10px', fontSize: 15 }}>{response.answer}</p>
          {response.referenced_sections.length ? (
            <div className="consult__refs">
              <span className="consult__refsLabel">Referenced:</span>
              {response.referenced_sections.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="tag tag--support consult__ref"
                  title={`Highlight the ${s} section`}
                  onClick={() => scrollToSection(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          ) : null}
          <div className="consult__audioRow">
            <button type="button" className="btn btn--outline" onClick={() => void listen()} disabled={audioStatus === 'loading'}>
              {audioStatus === 'loading' ? 'Preparing voice…' : '▶ Listen to explanation'}
            </button>
            {speaking ? <span className="badge badge--info">Speaking</span> : null}
            {audioError ? (
              <span role="alert" style={{ color: 'var(--danger)', fontSize: 13 }}>
                Speech synthesis unavailable — the text answer above remains available.
              </span>
            ) : null}
          </div>
          {audioUrl ? (
            <audio
              ref={audioRef}
              data-testid="consult-audio"
              className="consult__audio"
              controls
              preload="none"
              src={audioUrl}
              onPlay={() => setSpeaking(true)}
              onPause={() => setSpeaking(false)}
              onEnded={() => setSpeaking(false)}
            />
          ) : null}
          <p className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8 }}>
            answered by {response.model} · {response.timings.total_latency_ms} ms
          </p>
        </div>
      ) : null}
    </Section>
  )
}
