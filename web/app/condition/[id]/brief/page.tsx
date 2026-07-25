"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  FileText,
  HelpCircle,
  Loader2,
  TrendingUp,
} from "lucide-react"

import { ApiError, type Brief, api } from "@/lib/api"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { SummaryCard } from "@/components/summary-card"
import { Button } from "@/components/ui/button"

/**
 * The next-visit brief — the artifact the patient hands their doctor.
 *
 * This is the screen the whole product exists for, and the one the frontend
 * arrived without. What makes it worth a doctor's two minutes is not that it
 * summarises the last consultation, which is a memory aid anyone can build,
 * but that it is assembled from the interval that consultation opened: what
 * was agreed, what actually got done, what happened in between, and — the part
 * that costs the most to be honest about — what the record does not cover.
 *
 * Nothing here composes clinical text. Every line was written by the backend,
 * where the observations are pre-written in Python precisely so no model gets
 * the chance to turn "the test was due at week 7" into "the dose may be wrong".
 * This file renders strings and adds no judgement of its own.
 */

/** Status wording that does not soften a gap. See brief.py's prompt rules. */
const STATUS_LABEL: Record<string, string> = {
  done: "Done",
  not_done: "Not done",
  partial: "Partly done",
  changed: "Changed",
  unknown: "Never discussed",
}

const DIRECTION_TONE: Record<string, string> = {
  better: "text-success",
  worse: "text-warning-foreground",
  unchanged: "text-muted-foreground",
}

export default function BriefPage() {
  const params = useParams<{ id: string }>()
  const conditionId = params.id

  const [brief, setBrief] = React.useState<Brief | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const generate = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const row = await api.brief(conditionId)
      setBrief(row.content)
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Could not build the brief.",
      )
    } finally {
      setLoading(false)
    }
  }, [conditionId])

  React.useEffect(() => {
    void generate()
  }, [generate])

  return (
    <AppShell>
      <ScreenHeader
        title="Next-visit brief"
        subtitle="Bring this to your appointment"
        backHref={`/condition/${conditionId}`}
      />

      <Content className="flex flex-col gap-4 pb-10">
        {loading && (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Building your brief from the interval…
            </p>
          </div>
        )}

        {error && !loading && (
          <div className="flex flex-col gap-3 rounded-2xl border border-warning/40 bg-warning/10 p-4">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
              <p className="text-sm text-warning-foreground">{error}</p>
            </div>
            <Button variant="outline" size="sm" onClick={generate}>
              Try again
            </Button>
          </div>
        )}

        {brief && !loading && (
          <>
            <SummaryCard icon={<FileText />} title="What we agreed">
              <List
                items={brief.agreed.map((row) => row.text)}
                empty="Nothing was recorded as agreed at the last visit."
              />
            </SummaryCard>

            <SummaryCard icon={<CheckCircle2 />} title="What I did">
              {brief.did.length === 0 ? (
                <Empty>No check-in recorded whether any of it happened.</Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {brief.did.map((row, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      {/* The status is stated plainly and never softened —
                          a gap is the signal the doctor needs. */}
                      <span className="mt-0.5 shrink-0 rounded-md bg-accent px-1.5 py-0.5 text-[11px] font-medium text-accent-foreground">
                        {STATUS_LABEL[row.status] ?? row.status}
                      </span>
                      <span className="leading-snug">{row.text}</span>
                    </li>
                  ))}
                </ul>
              )}
            </SummaryCard>

            <SummaryCard icon={<CircleDashed />} title="What happened">
              {brief.happened.length === 0 ? (
                <Empty>Nothing was reported during the interval.</Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {brief.happened.map((row, i) => (
                    <li key={i} className="text-sm leading-snug">
                      {row.text}
                      {row.approx_timing && (
                        <span className="text-muted-foreground">
                          {" "}
                          ({row.approx_timing})
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </SummaryCard>

            <SummaryCard icon={<TrendingUp />} title="What changed">
              {brief.changed.length === 0 ? (
                <Empty>No change was recorded either way.</Empty>
              ) : (
                <ul className="flex flex-col gap-2">
                  {brief.changed.map((row, i) => (
                    <li key={i} className="text-sm leading-snug">
                      <span
                        className={
                          DIRECTION_TONE[row.direction] ?? "text-muted-foreground"
                        }
                      >
                        ●
                      </span>{" "}
                      {row.text}
                    </li>
                  ))}
                </ul>
              )}
            </SummaryCard>

            {brief.open_questions.length > 0 && (
              <SummaryCard icon={<HelpCircle />} title="Questions for the doctor">
                <List items={brief.open_questions} empty="" />
              </SummaryCard>
            )}

            {/* Rendered with the same weight as everything else, deliberately.
                A doctor reading this takes absence as "nothing to report", so
                what the record does not cover has to be said out loud. */}
            {brief.gaps.length > 0 && (
              <SummaryCard
                icon={<AlertCircle />}
                title="What this record does not cover"
                tone="warning"
              >
                <List items={brief.gaps} empty="" />
              </SummaryCard>
            )}

            <p className="px-1 text-xs leading-relaxed text-muted-foreground">
              Prepared by the patient from recorded consultations and
              self-reported check-ins. Not a medical record and not a clinical
              assessment.
            </p>

            <Button variant="outline" onClick={generate}>
              Rebuild from the latest record
            </Button>
          </>
        )}
      </Content>
    </AppShell>
  )
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return empty ? <Empty>{empty}</Empty> : null
  return (
    <ul className="flex flex-col gap-2">
      {items.map((text, i) => (
        <li key={i} className="text-sm leading-snug">
          {text}
        </li>
      ))}
    </ul>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>
}
