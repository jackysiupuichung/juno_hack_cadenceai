"use client"

import * as React from "react"
import Link from "next/link"
import { PhoneCall, X } from "lucide-react"

import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"

/**
 * The prompt that starts a check-in, styled as something that arrived.
 *
 * A check-in is not a thing patients go looking for. The population this
 * serves tires easily and forgets — that is the premise of the whole product —
 * so a call the patient has to remember to make is a call that does not happen.
 * It reads like a notification because that is what it is standing in for:
 * eventually a push notification lands at the planned week, and this is the
 * same moment rendered in-app.
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
    <section className="relative flex items-start gap-3 rounded-2xl border border-primary/25 bg-primary/5 p-3.5">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
        <PhoneCall className="size-4.5" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="pr-6 text-sm font-medium text-foreground">
          Time for your check-in
        </p>
        <p className="mt-0.5 text-pretty text-xs text-muted-foreground">
          {conditionName} · week {week ?? 0} · {open}{" "}
          {open === 1 ? "thing" : "things"} still open from your visit
        </p>
        <Button
          size="sm"
          className="mt-2.5"
          nativeButton={false}
          render={<Link href={`/condition/${conditionId}/check-in`} />}
        >
          <PhoneCall className="size-3.5" />
          Answer
        </Button>
      </div>

      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="absolute right-2.5 top-2.5 rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </section>
  )
}
