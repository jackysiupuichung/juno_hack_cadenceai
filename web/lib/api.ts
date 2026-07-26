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

// The fallback derives the host from the address bar rather than hardcoding
// localhost: a browser pointed at 127.0.0.1:3000 or a LAN IP would otherwise
// send every request to a literal "localhost" the backend's CORS allowlist
// rejects — and the store swallows that failure, so the app looks fine and
// only the server-fed sections silently vanish.
const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ??
  (typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000")

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

// The signed-in patient's token, held in module scope rather than threaded
// through every call. The store sets this once, on load and on sign-in/out;
// every request after that just picks up whatever is current.
let authToken: string | null = null

/** Called by the store: on load (from localStorage), after sign-up/sign-in,
 * and on log-out (with null). */
function setAuthToken(token: string | null) {
  authToken = token
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
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
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

/**
 * Everything the browser needs to open one voice call.
 *
 * `dynamic_variables` carries this interval into the agent's prompt — what was
 * agreed, which week it is, and, crucially, the safety boundary. The browser
 * agent speaks outside safety.py's reach, so the prohibitions and the verbatim
 * red-flag lines travel with the call rather than living only in the agent's
 * standing configuration, which is set elsewhere and can drift.
 */
export interface CheckInSession {
  agent_id: string
  conversation_token: string
  expires_in: number
  dynamic_variables: Record<string, string>
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

/**
 * A dated (or due) thing from the condition's chronology — see
 * backend/capture/events.py and the `events` table. What powers the
 * calendar: `occurred_at` is when it actually happened (however precisely
 * known), `due_at` is when a scheduled thing is due, and `when` is a
 * server-formatted string already carrying the right qualifier ("around
 * week two", "due 12 Aug").
 */
export interface CadenceEvent {
  id: string
  kind:
    | "visit"
    | "medication_start"
    | "medication_stop"
    | "dose_change"
    | "test_taken"
    | "test_result"
    | "symptom_onset"
    | "symptom_resolved"
    | "appointment"
    | "check_in"
    | "other"
  label: string
  occurred_at: string | null
  due_at: string | null
  precision: "exact" | "day" | "week" | "month" | "approx"
  source: "patient_reported" | "consultation" | "scheduled" | "derived"
  patient_words: string
  when: string
  reporting_delay_days: number | null
  context_ids: string[]
}

/**
 * A milestone the guideline expects, and where this interval sits on it.
 *
 * `status` is a window position and never a verdict — `past_expected` says
 * today is beyond `expected_by_week`, which is a fact about dates rather than
 * a claim about the treatment. All prose here is the guideline's own wording,
 * and `if_not_met` arrives empty until the window has actually passed.
 */
export interface TrajectoryMarker {
  id: string
  marker: string
  earliest_week: number | null
  expected_by_week: number | null
  expectation: string
  status: "too_early" | "in_window" | "past_expected"
  weeks_past_expected: number
  if_not_met: string
  source_id: string
}

export interface EventsResponse {
  today: string
  timeline: CadenceEvent[]
  upcoming: CadenceEvent[]
  overdue: CadenceEvent[]
  undated: CadenceEvent[]
  anchors: Record<string, string>
  fulfilled_count: number
  /** Null before the first visit: there is no week 0 to count from. */
  week: number | null
  /** Empty when the condition has no disease context to measure against. */
  trajectory: TrajectoryMarker[]
}

/**
 * One answer from the record's Q&A.
 *
 * `withheld` marks a question the backend declined to answer — advice, dosing
 * changes, anything over the CDS line — and its refusal text arrives in
 * `answer`, written server-side to be shown verbatim. `grounded: false` is
 * different and softer: the question was fair, the record just holds nothing
 * on it. `sources` names where a grounded answer came from, because a record
 * you can check is the difference between an answer and a chatbot.
 */
export interface AskResponse {
  answer: string
  grounded: boolean
  sources?: string[]
  withheld?: boolean
}

/** The signed-in patient's own account. See backend/loop/auth.py. */
export interface Account {
  id: string
  /** The login handle as well as the display name. */
  name: string
  date_of_birth: string | null
}

export interface AuthResponse {
  token: string
  patient: Account
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
  setAuthToken,

  signUp: (input: { name: string; password: string; date_of_birth: string }) =>
    post<AuthResponse>("auth/signup", input),

  signIn: (input: { name: string; password: string }) =>
    post<AuthResponse>("auth/login", input),

  /** Restores a session on a new device, or after local storage is cleared. */
  me: () => get<Account>("auth/me"),

  conditions: () => get<Condition[]>("conditions"),

  createCondition: (name: string) => post<Condition>("conditions", { name }),

  setConditionStatus: (id: string, status: "active" | "completed") =>
    post<Condition>(`conditions/${id}`, { status }),

  renameCondition: (id: string, name: string) =>
    post<Condition>(`conditions/${id}`, { name }),

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
    condition_id?: string
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

  /**
   * Mint a short-lived token so the browser can talk to the voice agent.
   *
   * The API key never leaves the server; this token is scoped to one
   * conversation and expires in ten minutes, so it is fetched at the moment
   * the patient starts a call rather than when the page loads.
   *
   * Throws ApiError with status 503 when no agent is provisioned, which the
   * calling page treats as "offer the form" rather than as a failure.
   */
  checkInSession: (conditionId: string) =>
    post<CheckInSession>("checkin/session", { condition_id: conditionId }),

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

  /**
   * Ask the record a question — scoped to one visit or to everything a
   * condition holds. The two scopes are one endpoint because they are one
   * capability with a different record behind it; which id is sent is the
   * whole difference.
   */
  ask: (
    input: { question: string } & (
      | { visit_id: string }
      | { condition_id: string }
    ),
  ) => post<AskResponse>("ask", input),

  /** The calendar's endpoint — one condition's whole chronology in one call. */
  events: (conditionId: string) =>
    get<EventsResponse>(`events?condition_id=${conditionId}`),

  /**
   * The "Delete my data" control. Cascades through every condition, visit,
   * check-in, and brief for this patient — the real erasure, not a local
   * cache clear.
   */
  reset: () => request<void>("reset", { method: "POST" }),
}
