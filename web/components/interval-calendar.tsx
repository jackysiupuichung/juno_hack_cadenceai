"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertTriangle,
  Stethoscope,
  Pill,
  FlaskConical,
  Activity,
  CalendarClock,
  CalendarDays,
  PhoneCall,
  CircleDot,
  ChevronRight,
} from "lucide-react"

import { api, type CadenceEvent, type EventsResponse, type TrajectoryMarker } from "@/lib/api"
import { formatDate } from "@/lib/dates"
import { cn } from "@/lib/utils"

/**
 * This interval, on the condition page: what the plan scheduled, what has
 * happened so far, and where the weeks sit against the expected course.
 *
 * Follows the visual language of the calendar page (app/calendar/page.tsx):
 * size-9 icon chips keyed by event kind, the server's own precision-hedged
 * `when` phrasing, destructive tint reserved for the one thing that is
 * genuinely outstanding. The month grid itself lives at /calendar across all
 * conditions; this is the single condition's slice of it.
 *
 * Three states that must never be silent: loading (skeleton), fetch failure
 * (a dashed card that says so), and only the genuinely-empty interval renders
 * nothing at all.
 */
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

/**
 * The server's `when` phrasing covers things that happened; for a due date
 * that nothing has happened against yet it falls back to "date not
 * established", which reads as a failure when the date is in fact known.
 * State the due date directly for those.
 */
function whenLabel(event: CadenceEvent): string {
  return event.due_at && !event.occurred_at
    ? `Due ${formatDate(event.due_at)}`
    : event.when
}

export function IntervalCalendar({ conditionId }: { conditionId: string }) {
  const [chronology, setChronology] = React.useState<EventsResponse | null>(null)
  const [state, setState] = React.useState<"loading" | "ready" | "error">("loading")

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const next = await api.events(conditionId)
        if (cancelled) return
        setChronology(next)
        setState("ready")
      } catch {
        if (!cancelled) setState("error")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [conditionId])

  if (state === "loading") {
    return <div className="h-24 animate-pulse rounded-2xl bg-muted" data-testid="interval-calendar" />
  }

  if (state === "error") {
    // A failed fetch used to render nothing, which reads as "there is no
    // calendar" when the truth is "the calendar could not be reached".
    return (
      <div
        data-testid="interval-calendar"
        className="rounded-2xl border border-dashed border-border bg-card px-5 py-6 text-center text-sm text-muted-foreground"
      >
        Couldn&apos;t load this interval&apos;s diary. Is the backend running?
      </div>
    )
  }

  if (!chronology) return null
  const { overdue, upcoming, timeline, trajectory, week } = chronology
  if (!overdue.length && !upcoming.length && !timeline.length && !trajectory.length) return null

  return (
    <div className="flex flex-col gap-5">
      <section data-testid="interval-calendar" className="flex flex-col gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          This interval
        </h2>

        {overdue.map((event) => (
          <article
            key={event.id}
            className="flex items-center gap-3 rounded-2xl border border-destructive/30 bg-destructive/5 p-3.5"
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
              <AlertTriangle className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{event.label}</p>
              <p className="mt-0.5 text-pretty text-xs text-muted-foreground">
                {`${whenLabel(event)} · not recorded`}
              </p>
            </div>
          </article>
        ))}

        {upcoming.map((event) => {
          const Icon = KIND_ICON[event.kind] ?? CircleDot
          return (
            <article
              key={event.id}
              className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3.5"
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Icon className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{event.label}</p>
                <p className="mt-0.5 text-pretty text-xs text-muted-foreground">{whenLabel(event)}</p>
              </div>
            </article>
          )
        })}

        {timeline.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-3.5">
            <ol className="flex flex-col">
              {timeline.map((event, i) => {
                const Icon = KIND_ICON[event.kind] ?? CircleDot
                return (
                  <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
                    {/* The connecting line of the chronology; the last row ends it. */}
                    {i < timeline.length - 1 && (
                      <span
                        aria-hidden
                        className="absolute left-[13px] top-7 h-[calc(100%-1.25rem)] w-px bg-border"
                      />
                    )}
                    <span className="z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                      <Icon className="size-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground">{event.label}</p>
                      <p className="mt-0.5 text-pretty text-xs text-muted-foreground">{event.when}</p>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>
        )}

        <Link
          href="/calendar"
          className="flex items-center justify-between rounded-2xl border border-border bg-card p-3.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
        >
          <span className="inline-flex items-center gap-2">
            <CalendarDays className="size-4 text-primary" />
            Open my calendar
          </span>
          <ChevronRight className="size-4 text-muted-foreground" />
        </Link>
      </section>

      {trajectory.length > 0 && <TrajectorySection markers={trajectory} week={week} />}
    </div>
  )
}

/**
 * The expected course, drawn as windows on a shared week axis.
 *
 * Each guideline milestone renders its window (earliest_week to
 * expected_by_week) as a band on a track, with a tick where this interval
 * currently sits. Deliberately quieter than the schedule above: nothing here
 * is something the patient failed to do — a window that has passed is the
 * body not having responded yet, which is information for the consultation,
 * not a task outstanding. So no destructive colour anywhere in this section,
 * and the only prose is the guideline's own (`expectation`, and `if_not_met`,
 * which the backend withholds until the window has actually gone).
 */
function TrajectorySection({
  markers,
  week,
}: {
  markers: TrajectoryMarker[]
  week: number | null
}) {
  const axisMax =
    Math.max(week ?? 0, ...markers.map((m) => m.expected_by_week ?? 0)) + 2

  const pct = (w: number) => `${Math.min(100, Math.max(0, (w / axisMax) * 100))}%`

  const STATUS_LABEL: Record<TrajectoryMarker["status"], string> = {
    too_early: "not yet expected",
    in_window: "in the usual window",
    past_expected: "past the usual window",
  }

  return (
    <section data-testid="trajectory-view" className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        The expected course
        {week !== null && (
          <span className="ml-1.5 font-normal normal-case tracking-normal">
            &middot; week {week}
          </span>
        )}
      </h2>

      <div className="rounded-3xl border border-border bg-card">
        {markers.map((marker, i) => (
          <article key={marker.id} className={cn("p-4", i > 0 && "border-t border-border")}>
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-medium text-foreground">{marker.marker}</p>
              <span className="mt-0.5 shrink-0 rounded-md bg-accent px-1.5 py-0.5 text-[11px] font-medium text-accent-foreground">
                {STATUS_LABEL[marker.status]}
              </span>
            </div>

            {/* The window on the week axis, with a tick at the current week. */}
            {marker.earliest_week !== null && marker.expected_by_week !== null && (
              <div className="mt-3">
                <div className="relative h-1.5 rounded-full bg-muted">
                  <span
                    aria-hidden
                    className="absolute inset-y-0 rounded-full bg-primary/30"
                    style={{
                      left: pct(marker.earliest_week),
                      width: `calc(${pct(marker.expected_by_week)} - ${pct(marker.earliest_week)})`,
                    }}
                  />
                  {week !== null && (
                    <span
                      aria-hidden
                      className="absolute -inset-y-1 w-0.5 rounded-full bg-foreground"
                      style={{ left: pct(week) }}
                    />
                  )}
                </div>
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                  <span>week {marker.earliest_week}</span>
                  <span>week {marker.expected_by_week}</span>
                </div>
              </div>
            )}

            <p className="mt-2 text-pretty text-xs leading-relaxed text-muted-foreground">
              {marker.expectation}
            </p>

            {/* Present only once the window has passed; empty until then. */}
            {marker.if_not_met && (
              <p className="mt-1.5 text-pretty text-xs font-medium text-foreground">
                {marker.if_not_met}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}
