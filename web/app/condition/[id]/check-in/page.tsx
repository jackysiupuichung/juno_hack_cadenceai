"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { ConversationProvider, useConversation } from "@elevenlabs/react"
import {
  AlertTriangle,
  ClipboardList,
  Loader2,
  Mic,
  PhoneCall,
  PhoneOff,
} from "lucide-react"

import { ApiError, type CheckInContext, type CheckInSession, api } from "@/lib/api"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * The check-in call: the agent phones, the patient talks, the record fills in.
 *
 * Voice is the point rather than a flourish. Fatigue is a core symptom of the
 * population this serves, and a thirty-second call gets an answer where a form
 * gets an abandoned tab. It also surfaces the thing forms never do — the
 * unprompted aside that turns out to be the finding.
 *
 * The conversation is shown as it happens. Partly so the patient can see they
 * are being heard, partly because this is a health record being written from
 * speech: someone should be able to watch what is going into it, and catch it
 * there and then if the agent misheard.
 *
 * Three rules this page holds to:
 *
 *   - The form is always reachable. Voice fails — no microphone, no agent
 *     provisioned, a dropped connection — and the loop must survive every one
 *     of those. Every failure path here ends at the form, never at a dead end.
 *   - Nothing clinical is composed in the browser. What the agent says comes
 *     from the backend's dynamic variables, red-flag lines included, verbatim.
 *   - The transcript is saved once. Ending a call can fire from a tap and a
 *     disconnect at the same moment, and two saves would be two check-ins.
 */

type Phase = "idle" | "connecting" | "live" | "saving" | "done" | "failed"

interface Turn {
  role: "user" | "agent"
  text: string
}

export default function CheckInPage() {
  return (
    <ConversationProvider>
      <CheckInCall />
    </ConversationProvider>
  )
}

function CheckInCall() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const conditionId = params.id

  const [context, setContext] = React.useState<CheckInContext | null>(null)
  const [phase, setPhase] = React.useState<Phase>("idle")
  const [error, setError] = React.useState<string | null>(null)
  const [turns, setTurns] = React.useState<Turn[]>([])
  const [showForm, setShowForm] = React.useState(false)

  // Read inside async callbacks that must not close over stale state.
  const turnsRef = React.useRef<Turn[]>([])
  const savedRef = React.useRef(false)
  const feedRef = React.useRef<HTMLDivElement>(null)

  // Declared before the hook so onDisconnect can reach the save defined below;
  // assigned once save exists.
  const saveRef = React.useRef<() => Promise<void>>(async () => {})

  const { startSession, endSession, status, isSpeaking } = useConversation({
    onMessage: ({ message, role }: { message: string; role: string }) => {
      const turn: Turn = {
        role: role === "user" ? "user" : "agent",
        text: message,
      }
      turnsRef.current = [...turnsRef.current, turn]
      setTurns(turnsRef.current)
    },
    onDisconnect: () => {
      // The agent hanging up on its own is the normal ending, not an edge
      // case — save then too. savedRef keeps a tap-plus-disconnect to one save.
      void saveRef.current()
    },
    onError: (message: string) => {
      setError(message || "The voice connection failed.")
      setPhase("failed")
    },
  })

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const ctx = await api.checkInContext(conditionId)
        if (!cancelled) setContext(ctx)
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not load this interval.",
          )
      }
    })()
    return () => {
      cancelled = true
    }
  }, [conditionId])

  // Keep the newest turn in view without stealing focus.
  React.useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [turns])

  const save = React.useCallback(async () => {
    // A disconnect can land alongside an explicit hang-up; only save once.
    if (savedRef.current) return
    savedRef.current = true

    const collected = turnsRef.current
    if (collected.length === 0) {
      setError("No conversation was recorded, so nothing has been saved.")
      setPhase("failed")
      return
    }

    setPhase("saving")
    // Speaker-labelled, because the backend maps what was said onto
    // commitments and the disease context's symptom vocabulary — and only the
    // patient's half of this is a report about them.
    const transcript = collected
      .map((t) => `${t.role === "user" ? "Patient" : "Cadence"}: ${t.text}`)
      .join("\n")

    try {
      await api.checkIn({ condition_id: conditionId, transcript })
      setPhase("done")
    } catch (err) {
      setError(
        err instanceof Error
          ? `The check-in could not be saved: ${err.message}`
          : "The check-in could not be saved.",
      )
      setPhase("failed")
    }
  }, [conditionId])

  saveRef.current = save

  async function begin() {
    setError(null)
    setTurns([])
    turnsRef.current = []
    savedRef.current = false
    setPhase("connecting")

    // Asked for on this tap rather than on mount: a page that grabs the
    // microphone the moment it opens is one people deny by reflex.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      setError(
        "Cadence could not use your microphone. Check your browser permissions, or answer in writing instead.",
      )
      setPhase("failed")
      return
    }

    // Fetched now, not on load, so a token cannot expire while the page sits
    // open — they are good for ten minutes.
    let session: CheckInSession
    try {
      session = await api.checkInSession(conditionId)
    } catch (err) {
      const voiceOff = err instanceof ApiError && err.status === 503
      setError(
        voiceOff
          ? "Voice check-in isn't set up on this server. You can answer in writing instead."
          : err instanceof Error
            ? `The call could not be started: ${err.message}`
            : "The call could not be started.",
      )
      setPhase("failed")
      return
    }

    try {
      await startSession({
        conversationToken: session.conversation_token,
        connectionType: "webrtc",
        dynamicVariables: session.dynamic_variables,
      })
      setPhase("live")
    } catch (err) {
      setError(
        err instanceof Error
          ? `The call could not be opened: ${err.message}`
          : "The call could not be opened.",
      )
      setPhase("failed")
    }
  }

  function hangUp() {
    void endSession()
    void saveRef.current()
  }

  if (showForm) {
    return (
      <CheckInForm
        conditionId={conditionId}
        context={context}
        onDone={() => router.replace(`/condition/${conditionId}`)}
      />
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

      <Content className="flex flex-1 flex-col gap-4 pb-8">
        {phase === "idle" && (
          <>
            <div className="flex flex-col items-center gap-3 pt-6 text-center">
              <div className="flex size-20 items-center justify-center rounded-full bg-primary/10 text-primary">
                <PhoneCall className="size-9" />
              </div>
              <div>
                <h1 className="text-xl font-semibold">Ready when you are</h1>
                <p className="mt-1 text-pretty text-sm text-muted-foreground">
                  A short call about how things have gone since your visit.
                  Usually under a minute.
                </p>
              </div>
            </div>

            {open.length > 0 && (
              <section className="rounded-2xl border border-border bg-card p-4">
                <h2 className="flex items-center gap-2 text-sm font-semibold">
                  <ClipboardList className="size-4 text-muted-foreground" />
                  What we&apos;ll cover
                </h2>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {open.slice(0, 4).map((c) => (
                    <li
                      key={c.commitment_id}
                      className="flex gap-2 text-sm leading-snug text-muted-foreground"
                    >
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/50" />
                      <span>{c.text}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="mt-auto flex flex-col gap-2">
              <Button size="lg" onClick={begin}>
                <Mic className="size-4" />
                Start the call
              </Button>
              <Button variant="ghost" onClick={() => setShowForm(true)}>
                Answer in writing instead
              </Button>
            </div>
          </>
        )}

        {(phase === "connecting" || phase === "live" || phase === "saving") && (
          <>
            <div className="flex flex-col items-center gap-2 pt-2 text-center">
              {/* The voice made visible: bars while Cadence speaks, one calm
                  breath while it listens. The status text carries the words. */}
              <div
                aria-hidden
                className={cn(
                  "flex size-16 items-center justify-center rounded-full transition-colors",
                  isSpeaking ? "bg-primary/20" : "bg-accent",
                )}
              >
                {isSpeaking ? (
                  <div className="flex h-8 items-center gap-1">
                    {["h-3", "h-6", "h-4", "h-5"].map((height, i) => (
                      <span
                        key={height}
                        className={cn("w-1 rounded-full bg-primary", height)}
                        style={{
                          animation: `eq-bar 0.9s ease-in-out ${i * 120}ms infinite`,
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <span
                    className="h-6 w-1 rounded-full bg-primary"
                    style={
                      status === "disconnected" || status === "error"
                        ? undefined // the call is over; the bar comes to rest
                        : { animation: "eq-breathe 2.2s ease-in-out infinite" }
                    }
                  />
                )}
              </div>
              <p role="status" className="text-sm font-medium">
                {phase === "connecting"
                  ? "Connecting…"
                  : phase === "saving"
                    ? "Saving your check-in…"
                    : status === "disconnected" || status === "error"
                      ? "Call ended"
                      : isSpeaking
                        ? "Cadence is speaking"
                        : status === "connected"
                          ? "Listening…"
                          : "Connecting…"}
              </p>
            </div>

            {/* The record being written, as it is written. */}
            <div
              ref={feedRef}
              aria-live="polite"
              className="flex min-h-40 flex-1 flex-col gap-2.5 overflow-y-auto rounded-2xl border border-border bg-card p-3.5"
            >
              {turns.length === 0 ? (
                <p className="m-auto text-center text-sm text-muted-foreground">
                  The conversation will appear here.
                </p>
              ) : (
                turns.map((t, i) => (
                  <div
                    key={i}
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug",
                      t.role === "user"
                        ? "self-end bg-primary text-primary-foreground"
                        : "self-start bg-muted text-foreground",
                    )}
                  >
                    {t.text}
                  </div>
                ))
              )}
            </div>

            {phase !== "saving" && (
              <Button variant="destructive" size="lg" onClick={hangUp}>
                <PhoneOff className="size-4" />
                End call
              </Button>
            )}
          </>
        )}

        {phase === "done" && (
          <div className="flex flex-1 flex-col">
            <div className="flex flex-col items-center gap-2 pt-6 text-center">
              <h1 className="text-xl font-semibold">Check-in saved</h1>
              <p className="text-pretty text-sm text-muted-foreground">
                {turns.length} exchange{turns.length === 1 ? "" : "s"} recorded.
                It will appear in your next-visit brief.
              </p>
            </div>
            <div className="mt-auto flex flex-col gap-2">
              <Button
                size="lg"
                onClick={() => router.replace(`/condition/${conditionId}/brief`)}
              >
                See the brief
              </Button>
              <Button
                variant="ghost"
                onClick={() => router.replace(`/condition/${conditionId}`)}
              >
                Done
              </Button>
            </div>
          </div>
        )}

        {phase === "failed" && (
          <div className="flex flex-1 flex-col gap-4">
            <div
              role="alert"
              className="flex items-start gap-2 rounded-2xl border border-warning/40 bg-warning/10 p-4"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
              <p className="text-sm text-warning-foreground">{error}</p>
            </div>
            {/* Every failure path ends here: the loop does not depend on voice. */}
            <div className="mt-auto flex flex-col gap-2">
              <Button size="lg" onClick={() => setShowForm(true)}>
                Answer in writing
              </Button>
              <Button variant="ghost" onClick={begin}>
                Try the call again
              </Button>
            </div>
          </div>
        )}
      </Content>

      {/* Same pattern as the landing page's orb-float. globals.css already
          collapses these under prefers-reduced-motion; at rest the bars simply
          stand at their staggered heights. */}
      <style>{`
        @keyframes eq-bar {
          0%, 100% { transform: scaleY(0.4); }
          50% { transform: scaleY(1); }
        }
        @keyframes eq-breathe {
          0%, 100% { transform: scaleY(0.55); opacity: 0.7; }
          50% { transform: scaleY(1); opacity: 1; }
        }
      `}</style>
    </AppShell>
  )
}

/** The fallback. Same record, typed — see the page comment above. */
function CheckInForm({
  conditionId,
  context,
  onDone,
}: {
  conditionId: string
  context: CheckInContext | null
  onDone: () => void
}) {
  const [outcomes, setOutcomes] = React.useState<Record<string, string>>({})
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const open = context?.open_commitments ?? []

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      await api.checkIn({
        condition_id: conditionId,
        // Only what they actually answered. An untouched row is left out
        // rather than sent as "unknown", so it stays open for the next call
        // instead of looking asked-and-settled — silence is not an answer.
        outcomes: Object.entries(outcomes).map(([commitment_id, status]) => ({
          commitment_id,
          status,
          patient_words: "",
          note: "",
        })),
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.")
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <ScreenHeader
        title="Check-in"
        subtitle={context ? `Week ${context.week} of this interval` : undefined}
        backHref={`/condition/${conditionId}`}
      />
      <Content className="flex flex-col gap-4 pb-10">
        {error && (
          <p
            role="alert"
            className="rounded-2xl border border-warning/40 bg-warning/10 p-4 text-sm text-warning-foreground"
          >
            {error}
          </p>
        )}

        {open.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center text-sm text-muted-foreground">
            Nothing is still open from your last visit.
          </p>
        ) : (
          open.map((c) => (
            <div
              key={c.commitment_id}
              className="rounded-2xl border border-border bg-card p-4"
            >
              <p className="text-sm leading-snug">{c.text}</p>
              <div className="mt-3 grid grid-cols-3 gap-2">
                {[
                  { value: "done", label: "Done" },
                  { value: "partial", label: "Partly" },
                  { value: "not_done", label: "Not yet" },
                ].map((s) => {
                  const active = outcomes[c.commitment_id] === s.value
                  return (
                    <button
                      key={s.value}
                      type="button"
                      aria-pressed={active}
                      onClick={() =>
                        setOutcomes((prev) =>
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
                        "rounded-xl border-2 px-2 py-3 text-sm font-medium transition-colors",
                        active
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border text-muted-foreground hover:border-primary/40",
                      )}
                    >
                      {s.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))
        )}

        <Button size="lg" onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save check-in
        </Button>
      </Content>
    </AppShell>
  )
}
