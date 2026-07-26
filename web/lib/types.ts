export type CareSetting = "GP" | "Hospital" | "Emergency" | "Specialist"

export type ConditionStatus = "active" | "completed"

export interface Profile {
  /** The login handle as well as the display name. */
  name: string
  dateOfBirth: string // ISO yyyy-mm-dd
}

export interface Consent {
  termsAccepted: boolean
  healthDataProcessing: boolean
  timestamp: string // ISO
}

export interface Settings {
  remindersEnabled: boolean
}

export interface Condition {
  id: string
  name: string
  status: ConditionStatus
  createdAt: string
}

export interface Medication {
  name: string
  dosage: string
  frequency: string
  duration: string
  instructions: string
}

export interface FuturePlan {
  follow_up_needed: boolean
  date_or_timeframe: string
  purpose: string
}

export interface Summary {
  patient_symptoms_summary: string
  doctor_diagnosis: string
  doctor_advice: string
  red_flags: string[]
  medications: Medication[]
  things_to_avoid: string[]
  lifestyle_advice: string[]
  future_plan: FuturePlan
}

export interface Appointment {
  id: string
  /** Optional: a consultation can exist on its own, unlinked to any condition. */
  conditionId?: string | null
  date: string
  careSetting: CareSetting
  organisationName?: string
  organisationAddress?: string
  doctorName?: string
  transcript: string
  summary: Summary | null
  createdAt: string
}

export interface Reminder {
  id: string
  conditionId?: string | null
  appointmentId: string
  date: string
  purpose: string
}

export interface AppData {
  profile: Profile | null
  /** The signed-in session's token. Set on sign-up/sign-in, cleared on log
   * out — everything else in this object is convenience cache; this is what
   * actually determines whose data the backend returns. */
  authToken: string | null
  consent: Consent | null
  settings: Settings
  conditions: Condition[]
  appointments: Appointment[]
  reminders: Reminder[]
}

export const EMPTY_SUMMARY: Summary = {
  patient_symptoms_summary: "",
  doctor_diagnosis: "",
  doctor_advice: "",
  red_flags: [],
  medications: [],
  things_to_avoid: [],
  lifestyle_advice: [],
  future_plan: { follow_up_needed: false, date_or_timeframe: "", purpose: "" },
}
