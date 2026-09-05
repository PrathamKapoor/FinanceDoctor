import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConsultPanel } from './ConsultPanel'
import { api } from '../api/client'
import type { ConsultationResponse, SpeechAudio } from '../api/types'

vi.mock('../api/client', () => ({
  api: {
    consult: vi.fn(),
    consultationAudio: vi.fn(),
    listConsultations: vi.fn(),
  },
}))

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>

const ANSWER =
  'On 2026-07-31, your payment failure rate rose from a 4.54% baseline to 21.75%.'

function consultResponse(): ConsultationResponse {
  return {
    consultation_id: 'cons_1',
    case_id: 'case_1',
    question: 'What happened?',
    answer: ANSWER,
    answer_type: 'incident',
    referenced_sections: ['incident', 'metrics'],
    generated_at: '2026-08-01T00:00:00',
    model: 'stub',
    timings: {
      context_build_ms: 1,
      model_latency_ms: 0,
      speech_latency_ms: 0,
      total_latency_ms: 5,
    },
  }
}

function audioResponse(): SpeechAudio {
  return {
    mime_type: 'audio/wav',
    data_base64: 'UklGRg==',
    byte_size: 44,
    duration_ms: 600,
    provider: 'stub',
    voice: 'stub-voice',
    consultation_id: 'cons_1',
    speech_latency_ms: 3,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.animate = vi.fn() as unknown as typeof Element.prototype.animate
})

describe('ConsultPanel', () => {
  it('renders typed input with examples and no microphone control', () => {
    render(<ConsultPanel caseId="case_1" />)
    expect(screen.getByText('Ask Financial Doctor')).toBeInTheDocument()
    expect(
      screen.getByText('Doctor, what happened to my payments?'),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(/Your question/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /microphone|🎙|record/i })).not.toBeInTheDocument()
  })

  it('asks a question and shows the grounded answer with referenced chips', async () => {
    mocked.consult.mockResolvedValue(consultResponse())
    render(<ConsultPanel caseId="case_1" />)
    await userEvent.type(screen.getByLabelText(/Your question/), 'What happened?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask Doctor' }))
    await waitFor(() => expect(mocked.consult).toHaveBeenCalledWith('case_1', 'What happened?'))
    await screen.findByText(ANSWER)
    expect(screen.getByText('incident')).toBeInTheDocument()
    expect(screen.getByText('metrics')).toBeInTheDocument()
  })

  it('scrolls to the referenced case section when a chip is clicked', async () => {
    mocked.consult.mockResolvedValue(consultResponse())
    document.body.innerHTML = '<div id="section-symptom">symptom</div>'
    render(<ConsultPanel caseId="case_1" />)
    await userEvent.type(screen.getByLabelText(/Your question/), 'What happened?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask Doctor' }))
    await screen.findByText(ANSWER)
    await userEvent.click(screen.getByText('incident'))
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('fetches audio on Listen and renders a non-autoplaying player', async () => {
    mocked.consult.mockResolvedValue(consultResponse())
    mocked.consultationAudio.mockResolvedValue(audioResponse())
    render(<ConsultPanel caseId="case_1" />)
    await userEvent.type(screen.getByLabelText(/Your question/), 'What happened?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask Doctor' }))
    await screen.findByText(ANSWER)
    await userEvent.click(screen.getByRole('button', { name: /Listen to explanation/ }))
    await waitFor(() =>
      expect(mocked.consultationAudio).toHaveBeenCalledWith('case_1', 'cons_1'),
    )
    const player = await screen.findByTestId('consult-audio')
    expect(player.getAttribute('src')).toBe('data:audio/wav;base64,UklGRg==')
    expect((player as HTMLAudioElement).autoplay).toBe(false)
  })

  it('shows a safe error state when consultation fails', async () => {
    mocked.consult.mockRejectedValue(new Error('HTTP 502 — boom'))
    render(<ConsultPanel caseId="case_1" />)
    await userEvent.type(screen.getByLabelText(/Your question/), 'What happened?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask Doctor' }))
    await screen.findByText(/Consultation temporarily unavailable/)
    expect(screen.queryByRole('button', { name: /Listen to explanation/ })).not.toBeInTheDocument()
  })
})
