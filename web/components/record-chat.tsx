"use client"

import * as React from "react"
import {
  AlertTriangle,
  RotateCcw,
  Send,
  ShieldCheck,
} from "lucide-react"

import { type AskResponse, api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/**
 * Ask the record a question, about one visit or about a whole condition.
 *
 * The two scopes are the same conversation with a different record behind it,
 * so they are one component. What changes is the question worth asking: on a
 * single visit it is "what did they say", and across a condition it is "what
 * am I on now, did I do the thing, when did this start" — the question a
 * patient actually has three weeks later, and the reason the condition scope
 * exists at all.
 *
 * Nothing here composes an answer. The backend decides what the record
 * supports, what it lacks, and what it will not say; this component's only
 * judgement is how honestly to show each of those three outcomes.
 */

type RecordChatProps =
  | { scope: "condition"; conditionId: string }
  | { scope: "visit"; visitId: string }

// The chips are the pitch for the feature: they show what kind of question a
// record can answer before the patient has thought of one.
const PROMPTS: Record<RecordChatProps["scope"], string[]> = {
  condition: [
    "What am I supposed to be taking right now?",
    "Did I ever get that test done?",
    "When did the symptoms start?",
  ],
  visit: ["What medication was I prescribed?", "What was the diagnosis?"],
}

type Entry =
  | { kind: "question"; text: string }
  | ({ kind: "answer" } & AskResponse)
  // A failed request keeps the question with it so "Ask again" can resend
  // exactly what was asked, without the patient retyping it.
  | { kind: "failure"; question: string; message: string }

export function RecordChat(props: RecordChatProps) {
  const [entries, setEntries] = React.useState<Entry[]>([])
  const [question, setQuestion] = React.useState("")
  const [asking, setAsking] = React.useState(false)
  const feedRef = React.useRef<HTMLDivElement>(null)

  // Keep the newest bubble in view without stealing focus — the same pattern
  // as the check-in call's live feed.
  React.useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [entries, asking])

  const send = React.useCallback(
    async (raw: string, addBubble: boolean) => {
      const q = raw.trim()
      if (!q || asking) return
      setAsking(true)
      // A retry replaces the failure notice rather than stacking a second
      // question bubble under the first.
      setEntries((prev) => {
        const kept = prev.filter((e) => e.kind !== "failure")
        return addBubble ? [...kept, { kind: "question", text: q }] : kept
      })
      try {
        const res = await api.ask(
          props.scope === "condition"
            ? { question: q, condition_id: props.conditionId }
            : { question: q, visit_id: props.visitId },
        )
        setEntries((prev) => [...prev, { kind: "answer", ...res }])
      } catch (err) {
        setEntries((prev) => [
          ...prev,
          {
            kind: "failure",
            question: q,
            message:
              err instanceof Error
                ? err.message
                : "Something went wrong asking your record.",
          },
        ])
      } finally {
        setAsking(false)
      }
    },
    [asking, props],
  )

  function submit() {
    const q = question.trim()
    if (!q || asking) return
    setQuestion("")
    void send(q, true)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div
        ref={feedRef}
        aria-live="polite"
        className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto rounded-2xl border border-border bg-card p-3.5"
      >
        {entries.length === 0 && !asking && (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground text-pretty">
              {props.scope === "condition"
                ? "Ask anything about what has been recorded for this condition."
                : "Ask anything about what was said at this visit."}
            </p>
            {PROMPTS[props.scope].map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => void send(p, true)}
                className="min-h-11 rounded-2xl border border-border bg-background px-3.5 py-2.5 text-left text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-muted/40 active:bg-muted/60"
              >
                {p}
              </button>
            ))}
          </div>
        )}

        {entries.map((e, i) => {
          if (e.kind === "question") {
            return (
              <div
                key={i}
                className="max-w-[85%] self-end rounded-2xl bg-primary px-3.5 py-2 text-sm leading-snug text-primary-foreground"
              >
                {e.text}
              </div>
            )
          }

          if (e.kind === "failure") {
            return (
              <div
                key={i}
                role="alert"
                className="flex max-w-[85%] flex-col gap-2 self-start rounded-2xl border border-warning/40 bg-warning/10 px-3.5 py-2.5"
              >
                <p className="flex items-start gap-2 text-sm leading-snug text-warning-foreground">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{e.message}</span>
                </p>
                <Button
                  variant="outline"
                  className="self-start"
                  disabled={asking}
                  onClick={() => void send(e.question, false)}
                >
                  <RotateCcw className="size-4" />
                  Ask again
                </Button>
              </div>
            )
          }

          // A withheld answer is the backend holding the CDS line. The refusal
          // text is the message — shown verbatim, styled as a quiet notice
          // rather than an answer, so declining reads as care and not failure.
          if (e.withheld) {
            return (
              <div
                key={i}
                className="flex max-w-[85%] items-start gap-2 self-start rounded-2xl border border-border bg-background px-3.5 py-2.5 text-sm leading-snug text-muted-foreground"
              >
                <ShieldCheck className="mt-0.5 size-4 shrink-0" />
                <p className="whitespace-pre-wrap">{e.answer}</p>
              </div>
            )
          }

          return (
            <div key={i} className="flex max-w-[85%] flex-col gap-1 self-start">
              <div className="rounded-2xl bg-muted px-3.5 py-2 text-sm leading-snug text-foreground">
                <p className="whitespace-pre-wrap">{e.answer}</p>
              </div>
              {/* Named plainly: an absence in the record is a finding the
                  patient can act on, not something to smooth over. */}
              {e.grounded === false && (
                <p className="px-1.5 text-xs text-muted-foreground">
                  Not found in your record
                </p>
              )}
              {/* Citations are what let the patient go and check. */}
              {e.grounded !== false && !!e.sources?.length && (
                <p className="px-1.5 text-xs text-muted-foreground">
                  From: {e.sources.join(" · ")}
                </p>
              )}
            </div>
          )
        })}

        {asking && (
          <div
            role="status"
            className="flex max-w-[85%] items-center gap-1 self-start rounded-2xl bg-muted px-3.5 py-3"
          >
            <span className="sr-only">Checking your record</span>
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                aria-hidden
                className="size-1.5 rounded-full bg-muted-foreground/60"
                style={{
                  animation: `chat-dot 1s ease-in-out ${delay}ms infinite`,
                }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit()
          }}
          placeholder="Ask a question"
          disabled={asking}
          aria-label="Your question"
          className="h-11 flex-1"
        />
        <Button
          size="icon"
          aria-label="Send question"
          disabled={asking || !question.trim()}
          onClick={submit}
        >
          <Send className="size-4" />
        </Button>
      </div>

      {/* The product principle, stated where the answers appear: this reads
          the record back, it never advises. */}
      <p className="text-xs text-muted-foreground text-pretty">
        Answers come only from your recorded visits. For medical advice, ask
        your doctor.
      </p>

      {/* globals.css already collapses animations under prefers-reduced-motion;
          at rest the dots simply stand still. */}
      <style>{`
        @keyframes chat-dot {
          0%, 100% { opacity: 0.35; transform: translateY(0); }
          50% { opacity: 1; transform: translateY(-3px); }
        }
      `}</style>
    </div>
  )
}
