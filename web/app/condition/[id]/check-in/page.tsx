"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { AlertTriangle, Loader2 } from "lucide-react"

import { ApiError, type CheckInContext, api } from "@/lib/api"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

/**
 * A check-in against the interval, not against a mood.
 *
 * What this replaced asked "better, same, or worse?" and stored the answer in
 * a single field on the appointment, so a second check-in overwrote the first.
 * That cannot hold a loop: it has no commitments, no interval, and nothing that
 * accumulates, which means the brief downstream would have had nothing made of
 * real follow-through to report.
 *
 * This asks about the things the patient actually agreed to, one row each, and
 * posts them as outcomes the backend keys to the commitment ids it extracted
 * from the consultation. Every answer is additive — a check-in at week two and
 * one at week six are two records, and the later one supersedes the earlier
 * only for the commitments it actually addressed.
 *
 * The voice check-in is the better experience and is the demo path. This is
 * the form fallback, which exists because a live voice call is the most
 * fragile thing in a demo and the loop must survive it failing.
 */

/** Mirrors the outcome statuses in check_in_turn.schema.json. */
const STATUSES: { value: string; label: string }[] = [
  { value: "done", label: "Done" },
  { value: "partial", label: "Partly" },
  { value: "not_done", label: "Not yet" },
]

export default function CheckInPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const conditionId = params.id

  const [context, setContext] = React.useState<CheckInContext | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // Keyed by commitment id. Absent means not addressed on this call, which is
  // recorded as absence rather than as "not done" — silence is not an answer.
  const [outcomes, setOutcomes] = React.useState<Record<string, string>>({})
  const [note, setNote] = React.useState("")

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const ctx = await api.checkInContext(conditionId)
        if (!cancelled) setContext(ctx)
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof ApiError || err instanceof Error
              ? err.message
              : "Could not load this interval.",
          )
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [conditionId])

  async function handleSave() {
    if (!context) return
    setSaving(true)
    setError(null)
    try {
      await api.checkIn({
        condition_id: conditionId,
        // Only commitments the patient actually answered for. An untouched
        // row is left out entirely rather than sent as "unknown", so it stays
        // open for the next call instead of looking asked-and-settled.
        outcomes: Object.entries(outcomes).map(([commitment_id, status]) => ({
          commitment_id,
          status,
          patient_words: "",
          note: "",
        })),
        note,
      })
      router.replace(`/condition/${conditionId}`)
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Could not save this check-in.",
      )
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      </AppShell>
    )
  }

  const open = context?.open_commitments ?? []

  return (
    <AppShell>
      <ScreenHeader
        title="Check-in"
        subtitle={context ? `Week ${context.week} of this interval` : undefined}
        backHref={`/condition/${conditionId}`}
      />

      <Content className="flex flex-col gap-5 pb-10">
        {error && (
          <div className="flex items-start gap-2 rounded-2xl border border-warning/40 bg-warning/10 p-4">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
            <p className="text-sm text-warning-foreground">{error}</p>
          </div>
        )}

        {context && (
          <div>
            <h1 className="text-balance text-xl font-semibold">
              How has it gone since your visit?
            </h1>
            <p className="mt-1 text-pretty text-sm text-muted-foreground">
              {context.is_first_check_in
                ? "This is the first check-in of the interval."
                : `Your last visit was ${context.visit_date}.`}
            </p>
          </div>
        )}

        {open.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
            Nothing is still open from your last visit.
          </p>
        ) : (
          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-muted-foreground">
              What you agreed
            </h2>
            {open.map((c) => (
              <div
                key={c.commitment_id}
                className="rounded-2xl border border-border bg-card p-4"
              >
                <p className="text-sm leading-snug">{c.text}</p>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {STATUSES.map((s) => {
                    const active = outcomes[c.commitment_id] === s.value
                    return (
                      <button
                        key={s.value}
                        type="button"
                        aria-pressed={active}
                        onClick={() =>
                          setOutcomes((prev) =>
                            // Tapping the active option clears it, so a
                            // mis-tap does not become a recorded answer.
                            prev[c.commitment_id] === s.value
                              ? Object.fromEntries(
                                  Object.entries(prev).filter(
                                    ([k]) => k !== c.commitment_id,
                                  ),
                                )
                              : { ...prev, [c.commitment_id]: s.value },
                          )
                        }
                        className={cn(
                          "rounded-xl border-2 px-2 py-2 text-xs font-medium transition-colors",
                          active
                            ? "border-primary bg-primary/5 text-foreground"
                            : "border-border text-muted-foreground hover:border-primary/40",
                        )}
                      >
                        {s.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </section>
        )}

        <div className="flex flex-col gap-2">
          <Label htmlFor="note">Anything else? (optional)</Label>
          <Textarea
            id="note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Anything new since your visit — even if it seems unrelated."
            rows={4}
          />
          {/* The open box is not decoration. The highest-value catch in this
              product is a symptom the patient would never connect to their
              condition, and it arrives here or not at all. */}
        </div>

        <Button size="lg" onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save check-in
        </Button>
      </Content>
    </AppShell>
  )
}
