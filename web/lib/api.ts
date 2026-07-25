/**
 * The Django backend, which is where every decision in this product is made.
 *
 * This file exists because the frontend arrived with its own summarisation
 * route, its own schema and its own prompt — a second implementation of work
 * the backend already does with Claude, the disease context, the red-flag
 * cluster count and the safety envelope. Two implementations of a clinical
 * boundary is one more than can be kept correct, and the one in the browser
 * had none of the machinery that makes the boundary hold.
 *
 * So nothing here decides anything. It moves JSON between the app and the API,
 * and every clinical judgement, every prompt and every schema stays in Python.
 */

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000"

/** A failure the UI can show a patient without leaking a stack trace. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}/api/${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    })
  } catch {
    // A dead backend is the single most likely failure in a demo, and "Failed
    // to fetch" tells a patient nothing. Name the actual cause.
    throw new ApiError(
      "Can't reach the Cadence server. Is the backend running?",
      0,
    )
  }

  if (res.status === 204) return undefined as T

  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      (body && (body.error || body.detail)) || `Request failed (${res.status}).`,
      res.status,
      body,
    )
  }
  return body as T
}

const get = <T,>(path: string) => request<T>(path)
const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) })

// --- Types the API actually returns -----------------------------------------
//
// Mirrors of the backend's schemas, narrowed to what the UI reads. Where a
// field is optional here it is because the backend genuinely may omit it, not
// because it is unknown — an interval with no plan really has no plan_brief.

export interface Medication {
  name: string
  dosage: string
  frequency: string
  duration: string
  instructions: string
}

export interface Commitment {
  id: string
  text: string
  type: string
  timeframe: string
  source_quote: string
  status: string
}

export interface VisitSummary {
  patient_symptoms_summary: string
  doctor_diagnosis: string
  doctor_advice: string
  red_flags: string[]
  medications: Medication[]
  things_to_avoid: string[]
  lifestyle_advice: string[]
  commitments: Array<Omit<Commitment, "id" | "status">>
  future_plan: {
    follow_up_needed: boolean
    date_or_timeframe: string
    purpose: string
  }
}

export interface Condition {
  id: string
  name: string
  status: "active" | "completed"
  created_at: string
  appointment_count: number
  reminder: { date_or_timeframe: string; purpose: string } | null
}

export interface Visit {
  id: string
  condition_id: string
  date: string
  care_setting: string
  clinician_name?: string
  organisation?: string
  organisation_address?: string
  transcript: string
  summary: VisitSummary | null
  created_at?: string
  commitments?: Commitment[]
}

/** The hero artifact. See backend/capture/brief.py. */
export interface Brief {
  agreed: Array<{ commitment_id?: string; text: string }>
  did: Array<{ commitment_id?: string; text: string; status: string }>
  happened: Array<{ text: string; approx_timing?: string }>
  changed: Array<{ text: string; direction: string }>
  open_questions: string[]
  gaps: string[]
}

/**
 * What ElevenLabs Scribe heard, after the backend has resolved who is who.
 *
 * `role_confidence` is worth surfacing rather than hiding: "low" means the
 * heuristics could not separate the speakers cleanly, and a summary built on
 * mis-assigned roles will attribute the patient's words to the clinician.
 */
export interface Transcription {
  /** Speaker-labelled lines: "DOCTOR: …" / "PATIENT: …". Prefer this. */
  dialogue: string
  /** The flat transcript, with no speaker labels. */
  text: string
  duration_seconds: number
  language_code?: string
  role_confidence: "high" | "low" | "none"
  speakers: Array<{ label: string; role: string }>
}

/** One row of a condition's merged feed: visits, check-ins and briefs. */
export interface TimelineEvent {
  kind: "visit" | "check_in" | "brief"
  date: string
  id: string
  care_setting?: string
  diagnosis_preview?: string
  preview?: string
}

export interface CheckInContext {
  week: number
  visit_date: string
  is_first_check_in: boolean
  interval_brief: string
  plan_brief: string
  plan: unknown | null
  disease_context: unknown
  open_commitments: Array<{
    commitment_id: string
    text: string
    type: string
    status: string
  }>
  already_reported: Array<{ watch_for: string; week: number }>
}

// --- Endpoints ---------------------------------------------------------------

export const api = {
  conditions: () => get<Condition[]>("conditions"),

  createCondition: (name: string) => post<Condition>("conditions", { name }),

  setConditionStatus: (id: string, status: "active" | "completed") =>
    post<Condition>(`conditions/${id}`, { status }),

  deleteCondition: (id: string) =>
    request<void>(`conditions/${id}`, { method: "DELETE" }),

  visit: (id: string) => get<Visit>(`visits/${id}`),

  deleteVisit: (id: string) => request<void>(`visits/${id}`, { method: "DELETE" }),

  /**
   * Audio in, speaker-labelled transcript out, via ElevenLabs Scribe.
   *
   * Posted to the backend rather than to a Next.js route so the API key stays
   * on one server and the diarization settings stay in one place.
   *
   * `dialogue` is preferred over `text` because the backend has already run
   * speaker inference over the diarized utterances and prefixed each line with
   * DOCTOR or PATIENT. Everything downstream depends on knowing who said what
   * — a commitment is something the patient agreed to, and an instruction is
   * something the clinician gave — so the unlabelled `text` is only a fallback
   * for when the roles could not be resolved at all.
   */
  transcribe: async (audio: Blob): Promise<Transcription> => {
    const form = new FormData()
    form.append("audio", audio, "consultation.webm")
    return request<Transcription>("transcribe", { method: "POST", body: form })
  },

  /**
   * Transcript in; a persisted visit, its Claude-structured summary, its
   * extracted commitments and the interval's plan out.
   *
   * The plan matters more than it looks: this single call is what opens the
   * interval, so a visit summarised here is one the check-ins already have an
   * agenda for.
   */
  summarise: (input: {
    condition_id: string
    transcript: string
    date?: string
    care_setting?: string
    clinician_name?: string
    organisation?: string
    organisation_address?: string
  }) =>
    post<
      Visit & {
        commitments: Commitment[]
        plan: unknown | null
        /**
         * Set when the interval could not be planned. The visit is still
         * durable and check-ins still run off the disease context, so this is
         * an offer to re-plan rather than a failure to report.
         */
        plan_error: string | null
      }
    >("summarise", input),

  checkInContext: (conditionId: string) =>
    get<CheckInContext>(`checkin/context?condition_id=${conditionId}`),

  checkInSession: (conditionId: string) =>
    post<{ token?: string; agent_id?: string; error?: string }>(
      "checkin/session",
      { condition_id: conditionId },
    ),

  /**
   * Record a check-in. Either a voice transcript, which the backend maps onto
   * commitments and the disease context's symptom vocabulary, or the form
   * fallback's already-structured outcomes.
   */
  checkIn: (input: {
    condition_id: string
    transcript?: string
    note?: string
    outcomes?: Array<{
      commitment_id: string
      status: string
      patient_words: string
      note: string
    }>
  }) => post<unknown>("checkin", input),

  /**
   * Build and persist the next-visit brief.
   *
   * The brief itself arrives under `content` — the row is the stored artifact
   * and the brief is its body, which is what lets a later interval point back
   * at the one the patient actually walked in with.
   */
  brief: (conditionId: string) =>
    post<{
      id: string
      condition_id: string
      generated_at: string
      content: Brief
    }>("brief", { condition_id: conditionId }),

  timeline: (conditionId: string) =>
    get<{
      condition: Condition
      open_commitments: Commitment[]
      events: TimelineEvent[]
      has_visits: boolean
    }>(`timeline?condition_id=${conditionId}`),

  ask: (conditionId: string, question: string) =>
    post<{ answer: string }>("ask", {
      condition_id: conditionId,
      question,
    }),
}
