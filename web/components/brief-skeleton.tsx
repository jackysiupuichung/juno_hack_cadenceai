"use client"

import * as React from "react"

import { Skeleton } from "@/components/ui/skeleton"

/**
 * The brief's first build is a Claude call over the whole interval and takes
 * the better part of a minute. A spinner makes that minute feel like a hang;
 * a sheet-shaped skeleton makes it feel like a document being written. Same
 * masthead, same primary rule, same ruled sections as BriefSheet, so the real
 * brief lands into the exact silhouette the patient has been looking at.
 */

/**
 * Honest stages, not fake progress. Each names work the backend really does
 * (read the visits, line them up against check-ins, note the record's edges),
 * and the last one sets the expectation that the wait is normal.
 */
const BUILD_STAGES = [
  "Reading your consultations…",
  "Lining up what was agreed against your check-ins…",
  "Noting what the record does not cover…",
  "Writing your brief. This can take a minute…",
]

const SECTION_ROWS = [2, 3, 2, 2]

export function BriefSkeleton() {
  const [stage, setStage] = React.useState(0)

  React.useEffect(() => {
    // Advances until it rests on the last message; a loop that starts over
    // would read as the build having failed and restarted.
    const timer = window.setInterval(() => {
      setStage((s) => Math.min(s + 1, BUILD_STAGES.length - 1))
    }, 7000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div
        role="status"
        className="flex items-center gap-2 self-start rounded-full bg-muted px-3 py-1.5 text-xs text-muted-foreground"
      >
        <span
          aria-hidden
          className="size-1.5 shrink-0 animate-pulse rounded-full bg-primary"
        />
        {BUILD_STAGES[stage]}
      </div>

      <div
        aria-hidden
        className="rounded-3xl border border-border bg-card p-5 shadow-md"
      >
        <h2 className="font-[family-name:var(--font-display)] text-2xl font-medium tracking-tight text-foreground">
          Next-visit brief
        </h2>
        <Skeleton className="mt-2 h-3 w-52" />

        <div className="mt-4 divide-y divide-border border-t-2 border-primary">
          {SECTION_ROWS.map((rows, i) => (
            <section key={i} className="flex flex-col gap-2.5 py-4">
              <div className="flex items-center gap-2">
                <Skeleton className="size-4 rounded" />
                <Skeleton className="h-3.5 w-32" />
              </div>
              {Array.from({ length: rows }, (_, r) => (
                <Skeleton
                  key={r}
                  className="h-3"
                  style={{ width: `${88 - ((i + r) % 3) * 14}%` }}
                />
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
