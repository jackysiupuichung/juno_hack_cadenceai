"use client"

import * as React from "react"
import type {
  AppData,
  Appointment,
  CheckIn,
  Condition,
  Consent,
  Profile,
  Reminder,
  Settings,
  Summary,
} from "@/lib/types"

const STORAGE_KEY = "consultation-companion:v1"

const DEFAULT_DATA: AppData = {
  profile: null,
  consent: null,
  settings: { remindersEnabled: false },
  conditions: [],
  appointments: [],
  reminders: [],
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

interface AppContextValue {
  data: AppData
  hydrated: boolean
  saveProfile: (profile: Profile) => void
  saveConsent: (consent: Consent) => void
  withdrawConsent: () => void
  setReminders: (enabled: boolean) => void
  addCondition: (name: string) => Condition
  completeCondition: (id: string) => void
  reopenCondition: (id: string) => void
  deleteCondition: (id: string) => void
  addAppointment: (
    input: Omit<Appointment, "id" | "createdAt" | "summary">,
  ) => Appointment
  updateAppointment: (id: string, patch: Partial<Appointment>) => void
  linkAppointment: (id: string, conditionId: string | null) => void
  setSummary: (id: string, transcript: string, summary: Summary) => void
  setCheckIn: (id: string, checkIn: CheckIn) => void
  deleteAppointment: (id: string) => void
  addReminder: (r: Omit<Reminder, "id">) => void
  deleteReminder: (id: string) => void
  clearAll: () => void
}

const AppContext = React.createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = React.useState<AppData>(DEFAULT_DATA)
  const [hydrated, setHydrated] = React.useState(false)

  React.useEffect(() => {
    setData(loadData())
    setHydrated(true)
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
      saveProfile: (profile) => setData((d) => ({ ...d, profile })),
      saveConsent: (consent) => setData((d) => ({ ...d, consent })),
      withdrawConsent: () => setData((d) => ({ ...d, consent: null })),
      setReminders: (enabled) =>
        setData((d) => ({ ...d, settings: { ...d.settings, remindersEnabled: enabled } })),
      addCondition: (name) => {
        const condition: Condition = {
          id: uid(),
          name: name.trim(),
          status: "active",
          createdAt: new Date().toISOString(),
        }
        setData((d) => ({ ...d, conditions: [condition, ...d.conditions] }))
        return condition
      },
      completeCondition: (id) =>
        setData((d) => ({
          ...d,
          conditions: d.conditions.map((c) =>
            c.id === id ? { ...c, status: "completed" } : c,
          ),
        })),
      reopenCondition: (id) =>
        setData((d) => ({
          ...d,
          conditions: d.conditions.map((c) =>
            c.id === id ? { ...c, status: "active" } : c,
          ),
        })),
      deleteCondition: (id) =>
        setData((d) => ({
          ...d,
          conditions: d.conditions.filter((c) => c.id !== id),
          // Keep the consultations themselves — just unlink them from the deleted condition.
          appointments: d.appointments.map((a) =>
            a.conditionId === id ? { ...a, conditionId: null } : a,
          ),
          reminders: d.reminders.map((r) =>
            r.conditionId === id ? { ...r, conditionId: null } : r,
          ),
        })),
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
      setCheckIn: (id, checkIn) =>
        setData((d) => ({
          ...d,
          appointments: d.appointments.map((a) =>
            a.id === id ? { ...a, checkIn } : a,
          ),
        })),
      deleteAppointment: (id) =>
        setData((d) => ({
          ...d,
          appointments: d.appointments.filter((a) => a.id !== id),
          reminders: d.reminders.filter((r) => r.appointmentId !== id),
        })),
      addReminder: (r) =>
        setData((d) => ({
          ...d,
          reminders: [...d.reminders.filter((x) => x.appointmentId !== r.appointmentId), { ...r, id: uid() }],
        })),
      deleteReminder: (id) =>
        setData((d) => ({ ...d, reminders: d.reminders.filter((r) => r.id !== id) })),
      clearAll: () => {
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
