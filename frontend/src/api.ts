const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${options?.method || 'GET'} ${path} failed: ${res.status} ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

function json(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export interface Commitment {
  id: string
  text: string
  type: 'medication' | 'test' | 'watch_for' | 'followup' | 'lifestyle'
  timeframe: string
  source_quote: string
  status: 'pending' | 'done' | 'not_done' | 'changed'
  created_at: string
}

export interface TimelineEvent {
  kind: 'visit' | 'check_in' | 'brief'
  date: string
  id: string
  care_setting?: string
  diagnosis_preview?: string
  preview?: string
}

export interface Timeline {
  condition: { id: string; name: string }
  open_commitments: Commitment[]
  events: TimelineEvent[]
  has_visits: boolean
}

export interface VisitSummary {
  patient_symptoms_summary: string
  doctor_diagnosis: string
  doctor_advice: string
  red_flags: string[]
  medications: { name: string; dosage: string; frequency: string; duration: string; instructions: string }[]
  things_to_avoid: string[]
  lifestyle_advice: string[]
  future_plan: { follow_up_needed: boolean; date_or_timeframe: string; purpose: string }
}

export interface Visit {
  id: string
  date: string
  care_setting: string
  clinician_name: string
  organisation: string
  transcript: string
  summary: VisitSummary
  commitments: Commitment[]
  created_at: string
}

export interface BriefContent {
  agreed: { commitment_id: string; text: string }[]
  did: { commitment_id: string; text: string; status: string }[]
  happened: { text: string; approx_timing: string }[]
  changed: { text: string; direction: string }[]
  open_questions: string[]
  gaps: string[]
}

export interface Brief {
  id: string
  generated_at: string
  content: BriefContent
}

export const api = {
  timeline: () => request<Timeline>('/timeline'),

  transcribe: (audio: Blob) => {
    const form = new FormData()
    form.append('audio', audio, 'recording.webm')
    return request<{ text: string; dialogue: string }>('/transcribe', { method: 'POST', body: form })
  },

  summarise: (data: {
    transcript: string
    date: string
    care_setting: string
    clinician_name?: string
    organisation?: string
  }) => request<Visit>('/summarise', json(data)),

  checkin: (data: { transcript?: string; outcomes?: { commitment_id: string; status: string; note: string }[] }) =>
    request<unknown>('/checkin', json(data)),

  brief: () => request<Brief>('/brief', { method: 'POST' }),

  reset: () => request<void>('/reset', { method: 'POST' }),
}
