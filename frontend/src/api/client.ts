import type {
  CaseView,
  ConsultationRecord,
  ConsultationResponse,
  HealthStatus,
  SpeechAudio,
} from './types'

// The backend base URL. Empty string means "same origin" (resolved through the
// Vite dev proxy in development). Override with VITE_API_BASE_URL for a build
// served from a different host.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = `${detail} — ${body.detail}`
    } catch {
      // non-JSON error body; keep the HTTP status text.
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export interface StartOptions {
  seed?: number
  num_orders?: number
  num_customers?: number
}

export const api = {
  getHealth(): Promise<HealthStatus> {
    return request<HealthStatus>('/health')
  },

  startCase(options: StartOptions = {}): Promise<CaseView> {
    return request<CaseView>('/demo/case/start', {
      method: 'POST',
      body: JSON.stringify(options),
    })
  },

  getCase(caseId: string): Promise<CaseView> {
    return request<CaseView>(`/demo/case/${caseId}`)
  },

  approve(caseId: string, decidedBy: string, reason?: string): Promise<CaseView> {
    return request<CaseView>(`/demo/case/${caseId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ decided_by: decidedBy, reason }),
    })
  },

  reject(caseId: string, decidedBy: string, reason?: string): Promise<CaseView> {
    return request<CaseView>(`/demo/case/${caseId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ decided_by: decidedBy, reason }),
    })
  },

  execute(caseId: string): Promise<CaseView> {
    return request<CaseView>(`/demo/case/${caseId}/execute`, { method: 'POST' })
  },

  simulate(caseId: string): Promise<CaseView> {
    return request<CaseView>(`/demo/case/${caseId}/simulate`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  consult(caseId: string, question: string): Promise<ConsultationResponse> {
    return request<ConsultationResponse>(`/demo/case/${caseId}/consult`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    })
  },

  listConsultations(caseId: string): Promise<{ case_id: string; consultations: ConsultationRecord[] }> {
    return request<{ case_id: string; consultations: ConsultationRecord[] }>(
      `/demo/case/${caseId}/consultations`,
    )
  },

  consultationAudio(caseId: string, consultationId: string): Promise<SpeechAudio> {
    return request<SpeechAudio>(`/demo/case/${caseId}/consultations/${consultationId}/audio`, {
      method: 'POST',
    })
  },
}