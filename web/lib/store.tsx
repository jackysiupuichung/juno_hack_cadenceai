"use client"

import * as React from "react"
import type {
  AppData,
  Appointment,
  Condition,
  Consent,
  Reminder,
  Settings,
  Summary,
} from "@/lib/types"
import { type Account, type TimelineEvent, type Visit as ApiVisit, api } from "@/lib/api"

const STORAGE_KEY = "consultation-companion:v1"

const DEFAULT_DATA: AppData = {
  profile: null,
  authToken: null,
  consent: null,
  settings: { remindersEnabled: false },
  conditions: [],
  appointments: [],
  reminders: [],
}

/** An account response in the shape the local profile already renders. */
function toProfile(account: Account, fallbackDateOfBirth = "") {
  return {
    name: account.name,
    dateOfBirth: account.date_of_birth ?? fallbackDateOfBirth,
  }
}

function loadData(): AppData {
  if (typeof window === "undefined") return DEFAULT_DATA
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_DATA
    return { ...DEFAULT_DATA, ...(JSON.parse(raw) as AppData) }
  } catch {
    return DEFAULT_DATA
  }
}

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

/**
 * Replace the clinical half of the store with what Supabase holds.
 *
 * Ids come from the server, which is the point: `/api/summarise`, the plan,
 * the check-ins and the brief all key off a condition id that only the backend
 * can mint. A locally-generated id would summarise into a 404, and the two
 * halves of the record would drift apart with no way to reconcile them.
 */
async function syncFromServer(
  setData: React.Dispatch<React.SetStateAction<AppData>>,
) {
  try {
    const conditions = await api.conditions()

    // The timeline lists a condition's visits by id; the full summary for each
    // is then fetched per visit. It is more requests than one bulk endpoint
    // would be, and it uses only endpoints that already exist — worth it at
    // this size, where a patient has a handful of visits, not hundreds.
    const timelines = await Promise.all(
      conditions.map((c) =>
        api.timeline(c.id).catch(() => ({ events: [] as TimelineEvent[] })),
      ),
    )
    const visitIds = timelines.flatMap((t) =>
      (t.events ?? []).filter((e) => e.kind === "visit").map((e) => e.id),
    )
    const visits = await Promise.all(
      visitIds.map((id) => api.visit(id).catch(() => null)),
    )

    setData((d) => ({
      ...d,
      conditions: conditions.map((c) => ({
        id: c.id,
        name: c.name,
        status: c.status,
        createdAt: c.created_at,
      })),
      appointments: visits.filter(Boolean).map((v) => toAppointment(v!)),
    }))
  } catch {
    // Offline, or the backend is not running. The cached record stands; every
    // screen that needs the server surfaces its own error when it calls one.
  }
}

/** A backend visit in the shape the existing screens already render. */
function toAppointment(v: ApiVisit): Appointment {
  return {
    id: v.id,
    conditionId: v.condition_id ?? null,
    date: (v.date ?? "").slice(0, 10),
    careSetting: (v.care_setting
      ? v.care_setting.charAt(0).toUpperCase() + v.care_setting.slice(1)
      : "GP") as Appointment["careSetting"],
    organisationName: v.organisation || undefined,
    doctorName: v.clinician_name || undefined,
    transcript: v.transcript ?? "",
    summary: (v.summary as Summary | null) ?? null,
    createdAt: v.created_at ?? v.date ?? "",
  }
}

interface AppContextValue {
  data: AppData
  hydrated: boolean
  signUp: (input: { name: string; password: string; dateOfBirth: string }) => Promise<void>
  signIn: (input: { name: string; password: string }) => Promise<void>
  saveConsent: (consent: Consent) => void
  withdrawConsent: () => void
  logOut: () => void
  deleteAllData: () => Promise<void>
  setReminders: (enabled: boolean) => void
  addCondition: (name: string) => Promise<Condition>
  completeCondition: (id: string) => void
  reopenCondition: (id: string) => void
  deleteCondition: (id: string) => void
  addAppointment: (
    input: Omit<Appointment, "id" | "createdAt" | "summary">,
  ) => Appointment
  updateAppointment: (id: string, patch: Partial<Appointment>) => void
  linkAppointment: (id: string, conditionId: string | null) => void
  setSummary: (id: string, transcript: string, summary: Summary) => void
  deleteAppointment: (id: string) => void
  addReminder: (r: Omit<Reminder, "id">) => void
  deleteReminder: (id: string) => void
}

const AppContext = React.createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = React.useState<AppData>(DEFAULT_DATA)
  const [hydrated, setHydrated] = React.useState(false)

  React.useEffect(() => {
    const local = loadData()
    api.setAuthToken(local.authToken)
    setData(local)
    setHydrated(true)

    // Conditions and visits are the backend's, not this device's. They are
    // merged in after the local read rather than instead of it so the app
    // renders immediately from cache and corrects itself a moment later —
    // and so a backend that is down degrades to the last known record rather
    // than to an empty one. Skipped with no token: every request would just
    // 401, and there is nothing to merge in for a session that hasn't signed
    // in yet.
    //
    // Consent and the reminders toggle stay local — device settings, not
    // part of the account.
    if (local.authToken) void syncFromServer(setData)
  }, [])

  React.useEffect(() => {
    if (!hydrated) return
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch {
      // ignore quota / private mode errors
    }
  }, [data, hydrated])

  const value = React.useMemo<AppContextValue>(() => {
    return {
      data,
      hydrated,
      // Creates the real account the rest of the record hangs off. Resets to
      // DEFAULT_DATA first (not just profile/token) so a second account
      // created in the same browser never starts with the previous one's
      // cached conditions still sitting in state.
      signUp: async ({ name, password, dateOfBirth }) => {
        const { token, patient } = await api.signUp({
          name,
          password,
          date_of_birth: dateOfBirth,
        })
        api.setAuthToken(token)
        setData(() => ({
          ...DEFAULT_DATA,
          authToken: token,
          profile: toProfile(patient, dateOfBirth),
        }))
        await syncFromServer(setData)
      },
      // Same reset-then-repopulate shape as signUp — this is the flow that
      // makes logging back in actually show the account's own data again,
      // rather than whatever the last session on this device happened to be.
      signIn: async ({ name, password }) => {
        const { token, patient } = await api.signIn({ name, password })
        api.setAuthToken(token)
        setData(() => ({
          ...DEFAULT_DATA,
          authToken: token,
          profile: toProfile(patient),
        }))
        await syncFromServer(setData)
      },
      saveConsent: (consent) => setData((d) => ({ ...d, consent })),
      // Stops health-data processing without touching what's already on
      // record. Distinct from deletion: this is "don't process going
      // forward", not "erase what happened".
      withdrawConsent: () => setData((d) => ({ ...d, consent: null })),
      // Signs this device out. The account and its data stay on the server;
      // signing back in via /signin restores them.
      logOut: () => {
        api.setAuthToken(null)
        setData((d) => ({ ...d, authToken: null, profile: null, consent: null }))
      },
      setReminders: (enabled) =>
        setData((d) => ({ ...d, settings: { ...d.settings, remindersEnabled: enabled } })),
      // The id has to come from the server. Everything the interval is made
      // of — the plan, the check-ins, the brief — is keyed to it, so a locally
      // minted id would summarise into a 404 and strand the record.
      addCondition: async (name) => {
        const created = await api.createCondition(name.trim())
        const condition: Condition = {
          id: created.id,
          name: created.name,
          status: created.status,
          createdAt: created.created_at,
        }
        setData((d) => ({ ...d, conditions: [condition, ...d.conditions] }))
        return condition
      },
      // Written through to the server, then applied locally so the screen
      // responds immediately. A failed write leaves the local state alone
      // rather than showing a change the record did not take.
      completeCondition: (id) => {
        void api.setConditionStatus(id, "completed").then(() =>
          setData((d) => ({
            ...d,
            conditions: d.conditions.map((c) =>
              c.id === id ? { ...c, status: "completed" } : c,
            ),
          })),
        )
      },
      reopenCondition: (id) => {
        void api.setConditionStatus(id, "active").then(() =>
          setData((d) => ({
            ...d,
            conditions: d.conditions.map((c) =>
              c.id === id ? { ...c, status: "active" } : c,
            ),
          })),
        )
      },
      deleteCondition: (id) => {
        // The backend cascades: the condition, its visits, commitments,
        // check-ins and briefs all go. That is what a patient asking to erase
        // a condition means, and leaving orphaned visits behind locally would
        // misrepresent what was actually deleted.
        void api.deleteCondition(id).then(() =>
          setData((d) => ({
            ...d,
            conditions: d.conditions.filter((c) => c.id !== id),
            appointments: d.appointments.filter((a) => a.conditionId !== id),
            reminders: d.reminders.filter((r) => r.conditionId !== id),
          })),
        )
      },
      addAppointment: (input) => {
        const appointment: Appointment = {
          ...input,
          id: uid(),
          summary: null,
          createdAt: new Date().toISOString(),
        }
        setData((d) => ({ ...d, appointments: [appointment, ...d.appointments] }))
        return appointment
      },
      updateAppointment: (id, patch) =>
        setData((d) => ({
          ...d,
          appointments: d.appointments.map((a) =>
            a.id === id ? { ...a, ...patch } : a,
          ),
        })),
      linkAppointment: (id, conditionId) =>
        setData((d) => ({
          ...d,
          appointments: d.appointments.map((a) =>
            a.id === id ? { ...a, conditionId } : a,
          ),
          // Keep any linked reminder's condition in sync.
          reminders: d.reminders.map((r) =>
            r.appointmentId === id ? { ...r, conditionId } : r,
          ),
        })),
      setSummary: (id, transcript, summary) =>
        setData((d) => ({
          ...d,
          appointments: d.appointments.map((a) =>
            a.id === id ? { ...a, transcript, summary } : a,
          ),
        })),
      // Per-appointment erasure, which the Settings screen offers as a right
      // rather than a convenience — so it has to delete the server's copy,
      // not just this device's view of it.
      deleteAppointment: (id) => {
        void api.deleteVisit(id).then(() =>
          setData((d) => ({
            ...d,
            appointments: d.appointments.filter((a) => a.id !== id),
            reminders: d.reminders.filter((r) => r.appointmentId !== id),
          })),
        )
      },
      addReminder: (r) =>
        setData((d) => ({
          ...d,
          reminders: [...d.reminders.filter((x) => x.appointmentId !== r.appointmentId), { ...r, id: uid() }],
        })),
      deleteReminder: (id) =>
        setData((d) => ({ ...d, reminders: d.reminders.filter((r) => r.id !== id) })),
      // The real erasure: the backend cascade first, so a failed request
      // leaves the record intact rather than clearing the device's view of
      // data that was never actually deleted. The account row itself is part
      // of that cascade, so the username is free to sign up again afterwards.
      deleteAllData: async () => {
        await api.reset()
        api.setAuthToken(null)
        try {
          window.localStorage.removeItem(STORAGE_KEY)
        } catch {
          // ignore
        }
        setData(DEFAULT_DATA)
      },
    }
  }, [data, hydrated])

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = React.useContext(AppContext)
  if (!ctx) throw new Error("useApp must be used within AppProvider")
  return ctx
}

// Selectors / helpers
function byNewest(a: Appointment, b: Appointment) {
  return a.date < b.date ? 1 : a.date > b.date ? -1 : b.createdAt.localeCompare(a.createdAt)
}

/**
 * An appointment that hasn't happened yet — a date in the diary rather than a
 * consultation on the record.
 *
 * It has no transcript and no summary because there is nothing to transcribe
 * until it takes place, which is what distinguishes it: a consultation
 * recorded this morning is already in the past, so a date test alone would
 * misjudge it. The date is checked too, so a visit that happened but was never
 * recorded still reads as past rather than being labelled "upcoming" forever.
 */
export function isUpcoming(appointment: Appointment): boolean {
  if (appointment.summary || appointment.transcript) return false
  return appointment.date >= new Date().toISOString().slice(0, 10)
}

/** Whole days from today until an upcoming appointment. Negative once past. */
export function daysUntil(iso: string): number {
  const then = new Date(`${iso.slice(0, 10)}T00:00:00`)
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  return Math.round((then.getTime() - now.getTime()) / 86_400_000)
}

/** "Today" / "Tomorrow" / "In 4 days" — how far off the appointment is. */
export function untilLabel(iso: string): string {
  const days = daysUntil(iso)
  if (days <= 0) return "Today"
  if (days === 1) return "Tomorrow"
  if (days < 7) return `In ${days} days`
  if (days < 14) return "Next week"
  return `In ${Math.round(days / 7)} weeks`
}

export function appointmentsForCondition(data: AppData, conditionId: string) {
  return data.appointments.filter((a) => a.conditionId === conditionId).sort(byNewest)
}

/** All consultations, newest first. */
export function allAppointments(data: AppData) {
  return [...data.appointments].sort(byNewest)
}

/** Consultations not yet linked to any condition, newest first. */
export function unlinkedAppointments(data: AppData) {
  return data.appointments.filter((a) => !a.conditionId).sort(byNewest)
}

export function conditionName(data: AppData, conditionId?: string | null) {
  if (!conditionId) return null
  return data.conditions.find((c) => c.id === conditionId)?.name ?? null
}
