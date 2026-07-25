// Onboarding/consent/settings are device-local by design (GDPR data
// minimisation) — they gate *this device's* recording/UI behaviour, not
// health data, which lives in Supabase via the backend.

export interface Profile {
  name: string
  dateOfBirth: string
}

export interface Consent {
  termsAccepted: boolean
  healthDataProcessing: boolean
  timestamp: string
}

export interface LocalSettings {
  remindersEnabled: boolean
}

const PROFILE_KEY = 'cadence.profile'
const CONSENT_KEY = 'cadence.consent'
const SETTINGS_KEY = 'cadence.settings'

export function getProfile(): Profile | null {
  const raw = localStorage.getItem(PROFILE_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setProfile(profile: Profile) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
}

export function getConsent(): Consent | null {
  const raw = localStorage.getItem(CONSENT_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setConsent(consent: Omit<Consent, 'timestamp'>) {
  localStorage.setItem(
    CONSENT_KEY,
    JSON.stringify({ ...consent, timestamp: new Date().toISOString() }),
  )
}

export function withdrawConsent() {
  localStorage.removeItem(CONSENT_KEY)
}

export function getSettings(): LocalSettings {
  const raw = localStorage.getItem(SETTINGS_KEY)
  return raw ? JSON.parse(raw) : { remindersEnabled: false }
}

export function setSettings(settings: LocalSettings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
}

export function ageFromDOB(dateOfBirth: string): number {
  const dob = new Date(dateOfBirth)
  const today = new Date()
  let age = today.getFullYear() - dob.getFullYear()
  const monthDiff = today.getMonth() - dob.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
    age--
  }
  return age
}

export function clearAllLocalData() {
  localStorage.removeItem(PROFILE_KEY)
  localStorage.removeItem(CONSENT_KEY)
  localStorage.removeItem(SETTINGS_KEY)
}
