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

function json(body: unknown, method = 'POST'): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export interface Patient {
  id: string
  name: string
  created_at: string
}

export interface Reminder {
  date_or_timeframe: string
  purpose: string
}

export interface Condition {
  id: string
  name: string
  status: 'active' | 'completed'
  created_at: string
  appointment_count: number
  reminder: Reminder | null
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
  condition: Condition
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
  organisation_address: string
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
  getPatient: () => request<Patient>('/patient'),
  setPatientName: (name: string) => request<Patient>('/patient', json({ name }, 'PATCH')),

  listConditions: () => request<Condition[]>('/conditions'),
  createCondition: (name: string) => request<Condition>('/conditions', json({ name })),
  setConditionStatus: (conditionId: string, status: 'active' | 'completed') =>
    request<Condition>(`/conditions/${conditionId}`, json({ status })),
  deleteCondition: (conditionId: string) =>
    request<void>(`/conditions/${conditionId}`, { method: 'DELETE' }),
  getVisit: (visitId: string) => request<Visit>(`/visits/${visitId}`),
  deleteVisit: (visitId: string) => request<void>(`/visits/${visitId}`, { method: 'DELETE' }),

  timeline: (conditionId: string) => request<Timeline>(`/timeline?condition_id=${conditionId}`),

  ask: (visitId: string, question: string) =>
    request<{ answer: string; grounded: boolean }>('/ask', json({ visit_id: visitId, question })),

  transcribe: (audio: Blob) => {
    const form = new FormData()
    form.append('audio', audio, 'recording.webm')
    return request<{ text: string; dialogue: string }>('/transcribe', { method: 'POST', body: form })
  },

  summarise: (data: {
    condition_id: string
    transcript: string
    date: string
    care_setting: string
    clinician_name?: string
    organisation?: string
    organisation_address?: string
  }) => request<Visit>('/summarise', json(data)),

  checkin: (data: {
    condition_id: string
    transcript?: string
    outcomes?: { commitment_id: string; status: string; note: string }[]
  }) => request<unknown>('/checkin', json(data)),

  brief: (conditionId: string) => request<Brief>('/brief', json({ condition_id: conditionId })),

  reset: () => request<void>('/reset', { method: 'POST' }),
}
