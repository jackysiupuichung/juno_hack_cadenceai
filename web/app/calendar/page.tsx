"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import {
  ChevronLeft,
  ChevronRight,
  Stethoscope,
  Pill,
  FlaskConical,
  Activity,
  CalendarClock,
  PhoneCall,
  CircleDot,
  AlertTriangle,
} from "lucide-react"
import { useApp } from "@/lib/store"
import type { Condition as LocalCondition } from "@/lib/types"
import { api, type CadenceEvent } from "@/lib/api"
import { formatDate } from "@/lib/dates"
import { cn } from "@/lib/utils"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"

const KIND_ICON: Record<CadenceEvent["kind"], typeof Stethoscope> = {
  visit: Stethoscope,
  medication_start: Pill,
  medication_stop: Pill,
  dose_change: Pill,
  test_taken: FlaskConical,
  test_result: FlaskConical,
  symptom_onset: Activity,
  symptom_resolved: Activity,
  appointment: CalendarClock,
  check_in: PhoneCall,
  other: CircleDot,
}

interface TaggedEvent extends CadenceEvent {
  conditionId: string
  conditionName: string
}

function toISODate(y: number, m: number, d: number) {
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`
}

// Three-letter names: single letters give a screen reader "S S" for two
// different days and force sighted users to count columns.
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

export default function CalendarPage() {
  const router = useRouter()
  const { data, hydrated } = useApp()

  const [loading, setLoading] = React.useState(true)
  const [upcoming, setUpcoming] = React.useState<TaggedEvent[]>([])
  const [overdue, setOverdue] = React.useState<TaggedEvent[]>([])
  const [dated, setDated] = React.useState<TaggedEvent[]>([])
  const [today, setToday] = React.useState<string>(new Date().toISOString().slice(0, 10))

  const cursorNow = new Date()
  const [cursor, setCursor] = React.useState(() => ({ y: cursorNow.getFullYear(), m: cursorNow.getMonth() }))
  const [selected, setSelected] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (hydrated && (!data.profile || !data.consent)) router.replace("/home")
  }, [hydrated, data.profile, data.consent, router])

  const conditions: LocalCondition[] = data.conditions

  React.useEffect(() => {
    if (!hydrated || conditions.length === 0) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    Promise.all(
      conditions.map(async (c) => {
        try {
          const res = await api.events(c.id)
          const tag = (e: CadenceEvent): TaggedEvent => ({ ...e, conditionId: c.id, conditionName: c.name })
          return { ...res, upcoming: res.upcoming.map(tag), overdue: res.overdue.map(tag), timeline: res.timeline.map(tag) }
        } catch {
          return null
        }
      }),
    ).then((results) => {
      if (cancelled) return
      const ok = results.filter((r): r is NonNullable<typeof r> => r !== null)
      setUpcoming(ok.flatMap((r) => r.upcoming).sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? "")))
      setOverdue(ok.flatMap((r) => r.overdue).sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? "")))
      setDated(ok.flatMap((r) => r.timeline))
      if (ok[0]) setToday(ok[0].today)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, conditions.length])

  if (!hydrated || !data.profile) {
    return (
      <AppShell>
        <ScreenHeader title="My calendar" backHref="/home" />
        <div role="status" className="flex flex-1 items-center justify-center">
          <span className="sr-only">Loading</span>
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const byDate = new Map<string, TaggedEvent[]>()
  for (const e of [...dated, ...upcoming, ...overdue]) {
    const key = (e.occurred_at ?? e.due_at ?? "").slice(0, 10)
    if (!key) continue
    const list = byDate.get(key) ?? []
    if (!list.some((x) => x.id === e.id)) list.push(e)
    byDate.set(key, list)
  }

  const first = new Date(cursor.y, cursor.m, 1)
  const daysInMonth = new Date(cursor.y, cursor.m + 1, 0).getDate()
  const startWeekday = first.getDay()
  const cells: (number | null)[] = [
    ...Array.from({ length: startWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]
  const monthLabel = first.toLocaleDateString("en-GB", { month: "long", year: "numeric" })
  const monthName = first.toLocaleDateString("en-GB", { month: "long" })

  const agenda = selected
    ? (byDate.get(selected) ?? [])
    : [...overdue, ...upcoming]

  return (
    <AppShell>
      <ScreenHeader title="My calendar" backHref="/home" />
      <Content className="flex flex-col gap-6 pb-10">
        {conditions.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center">
            <p className="font-medium">Nothing to show yet</p>
            <p className="mt-1 text-sm text-muted-foreground text-pretty">
              Follow-ups, tests and appointments will show up here once you have a condition with a consultation.
            </p>
          </div>
        ) : (
          <>
            <section className="rounded-2xl border border-border bg-card p-4">
              <div className="flex items-center justify-between px-1">
                <button
                  type="button"
                  aria-label="Previous month"
                  onClick={() => setCursor((c) => (c.m === 0 ? { y: c.y - 1, m: 11 } : { y: c.y, m: c.m - 1 }))}
                  className="flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                >
                  <ChevronLeft className="size-4" />
                </button>
                <p className="text-sm font-semibold tabular-nums text-foreground">{monthLabel}</p>
                <button
                  type="button"
                  aria-label="Next month"
                  onClick={() => setCursor((c) => (c.m === 11 ? { y: c.y + 1, m: 0 } : { y: c.y, m: c.m + 1 }))}
                  className="flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                >
                  <ChevronRight className="size-4" />
                </button>
              </div>

              <div className="mt-3 grid grid-cols-7 gap-y-1 text-center tabular-nums">
                {WEEKDAYS.map((w) => (
                  <span key={w} className="text-xs font-medium text-muted-foreground">
                    {w}
                  </span>
                ))}
                {cells.map((day, i) => {
                  if (day === null) return <span key={`empty-${i}`} />
                  const iso = toISODate(cursor.y, cursor.m, day)
                  const events = byDate.get(iso) ?? []
                  const hasOverdue = events.some((e) => overdue.some((o) => o.id === e.id))
                  const isToday = iso === today
                  const isSelected = selected === iso
                  return (
                    <button
                      key={iso}
                      type="button"
                      onClick={() => setSelected((s) => (s === iso ? null : iso))}
                      // The dot is colour-only and 4px; the label carries what
                      // the dot means so it isn't lost to a screen reader.
                      aria-label={`${day} ${monthName}, ${
                        events.length === 0
                          ? "no items"
                          : `${events.length} item${events.length === 1 ? "" : "s"}`
                      }${hasOverdue ? ", overdue" : ""}`}
                      aria-pressed={isSelected}
                      className="flex items-center justify-center py-1.5"
                    >
                      <span
                        className={cn(
                          "relative flex size-8 items-center justify-center rounded-full text-sm transition-colors",
                          isSelected
                            ? "bg-primary text-primary-foreground"
                            : isToday
                              ? "font-semibold text-primary ring-1 ring-primary/50"
                              : "text-foreground hover:bg-muted",
                        )}
                      >
                        {day}
                        {events.length > 0 && !isSelected && (
                          <span
                            className={cn(
                              "absolute bottom-0.5 size-1 rounded-full",
                              hasOverdue ? "bg-destructive" : "bg-primary",
                            )}
                          />
                        )}
                      </span>
                    </button>
                  )
                })}
              </div>
            </section>

            <section className="flex flex-col gap-3">
              <h2 className="text-sm font-semibold tabular-nums text-muted-foreground">
                {selected ? new Date(selected).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "Upcoming"}
              </h2>
              {loading ? (
                <div className="h-24 animate-pulse rounded-2xl bg-muted" />
              ) : agenda.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-border bg-card px-5 py-8 text-center text-sm text-muted-foreground">
                  {selected ? "Nothing on this day." : "Nothing due or overdue right now."}
                </div>
              ) : (
                <div className="flex flex-col gap-2.5">
                  {agenda.map((e) => {
                    const Icon = KIND_ICON[e.kind] ?? CircleDot
                    const isOverdue = overdue.some((o) => o.id === e.id)
                    return (
                      <Link
                        key={e.id}
                        href={`/condition/${e.conditionId}`}
                        className={cn(
                          "flex items-center gap-3 rounded-2xl border p-3.5",
                          isOverdue ? "border-destructive/30 bg-destructive/5" : "border-border bg-card",
                        )}
                      >
                        <div
                          className={cn(
                            "flex size-9 shrink-0 items-center justify-center rounded-full",
                            isOverdue ? "bg-destructive/15 text-destructive" : "bg-primary/10 text-primary",
                          )}
                        >
                          {isOverdue ? <AlertTriangle className="size-4" /> : <Icon className="size-4" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">{e.label}</p>
                          <p className="truncate text-xs text-muted-foreground">
                            {/* `when` covers what happened; for a due date nothing
                                has been recorded against it says "date not
                                established", though the date is known. */}
                            {`${e.due_at && !e.occurred_at ? `Due ${formatDate(e.due_at)}` : e.when} · ${e.conditionName}`}
                          </p>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              )}
            </section>
          </>
        )}
      </Content>
    </AppShell>
  )
}
