"use client"

import * as React from "react"
import Link from "next/link"
import { ChevronRight, PhoneCall, X } from "lucide-react"

import { api } from "@/lib/api"

/**
 * The prompt that starts a check-in: a due item at the top of the home screen.
 *
 * A check-in is not a thing patients go looking for. The population this
 * serves tires easily and forgets — that is the premise of the whole product —
 * so a call the patient has to remember to make is a call that does not happen.
 * It says "due today" rather than announcing itself, because a thing on a list
 * that is due is easier to act on than a thing demanding attention, and this
 * is standing in for the push notification that eventually lands at the
 * planned week.
 *
 * Deliberately dismissible. Something that cannot be cleared is nagging, and
 * the brief is explicit that chasing has a limit. Dismissal is per-session
 * rather than persisted — a check-in that matters at week 7 still matters
 * tomorrow, and burying it for good would lose it.
 */
export function CheckInNotification({
  conditionId,
  conditionName,
}: {
  conditionId: string
  conditionName: string
}) {
  const [week, setWeek] = React.useState<number | null>(null)
  const [open, setOpen] = React.useState<number>(0)
  const [dismissed, setDismissed] = React.useState(false)
  const [ready, setReady] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const ctx = await api.checkInContext(conditionId)
        if (cancelled) return
        setWeek(ctx.week)
        setOpen(ctx.open_commitments.length)
        // Nothing still open means nothing to ask about. Showing the prompt
        // anyway would spend the patient's attention on a call with no agenda.
        setReady(ctx.open_commitments.length > 0)
      } catch {
        // No visits yet, or the backend is unreachable. Either way there is no
        // interval to check in on, so the prompt simply does not appear.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [conditionId])

  if (!ready || dismissed) return null

  return (
    <section className="relative">
      {/* The whole card is the target, not just a button inside it. On a phone
          the card is what the thumb goes for, and a tap that lands next to the
          button rather than on it reads as the app ignoring you. */}
      <Link
        href={`/condition/${conditionId}/check-in`}
        className="flex items-center gap-3 rounded-2xl border border-primary/25 bg-primary/5 p-3.5 transition-colors hover:bg-primary/10 active:bg-primary/15"
      >
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
          <PhoneCall className="size-4.5" />
        </div>

        <div className="min-w-0 flex-1">
          <p className="pr-6 text-sm font-medium text-foreground">
            Check-in due today
          </p>
          <p className="mt-0.5 text-pretty text-xs text-muted-foreground">
            {conditionName} · week {week ?? 0} · {open}{" "}
            {open === 1 ? "thing" : "things"} still open from your visit
          </p>
        </div>

        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
      </Link>

      {/* Layered over the link rather than nested inside it: a button inside an
          anchor still navigates on tap, so dismissing would open the call. */}
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss check-in reminder"
        className="absolute right-2.5 top-2.5 rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </section>
  )
}
