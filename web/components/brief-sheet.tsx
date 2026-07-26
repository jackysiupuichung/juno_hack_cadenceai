import * as React from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  FileText,
  HelpCircle,
  TrendingUp,
} from "lucide-react"

import type { Brief } from "@/lib/api"
import { cn } from "@/lib/utils"

/**
 * The brief rendered as the document it is.
 *
 * Every other screen in this app is a stack of cards; this is one sheet — the
 * app's sole shadow-md, sole rounded-3xl and sole serif moment — because it is
 * the one thing the patient physically hands to another person. The sections
 * are ruled divisions of a single page, not six separate cards, and the "does
 * not cover" block keeps its warning tint inside the sheet: a doctor reads
 * absence as "nothing to report", so the record's edges have to be said out
 * loud, visibly.
 */

/** Status wording that does not soften a gap. See brief.py's prompt rules. */
const STATUS_LABEL: Record<string, string> = {
  done: "Done",
  not_done: "Not done",
  partial: "Partly done",
  changed: "Changed",
  unknown: "Never discussed",
}

/**
 * Status colour that matches the wording. One mint chip for every status made
 * "Not done" read like an achievement; a gap should look like a gap.
 */
const STATUS_TONE: Record<string, string> = {
  done: "bg-accent text-accent-foreground",
  partial: "bg-warning/15 text-warning-foreground",
  not_done: "bg-warning/25 text-warning-foreground",
  changed: "bg-accent text-accent-foreground",
  unknown: "bg-muted text-muted-foreground",
}

/** The direction dot's fill — the bg-* twin of the old text-* tone map. */
const DIRECTION_DOT: Record<string, string> = {
  better: "bg-success",
  worse: "bg-warning-foreground",
  unchanged: "bg-muted-foreground",
}

/**
 * Sections fade up in reading order on a fresh build only. A brief re-opened
 * from cache is a document being picked back up, not an unveiling, so it
 * renders settled.
 */
function reveal(animate: boolean, i: number): React.CSSProperties | undefined {
  if (!animate) return undefined
  return {
    animation: "fade-up 500ms var(--ease-out) both",
    animationDelay: `${i * 80}ms`,
  }
}

export function BriefSheet({
  brief,
  conditionName,
  patientName,
  animate,
}: {
  brief: Brief
  conditionName: string | null
  patientName: string | null
  animate: boolean
}) {
  const today = new Date().toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
  const meta = [
    conditionName,
    patientName ? `Prepared by ${patientName}` : null,
    today,
  ]
    .filter(Boolean)
    .join(" · ")

  const sections: Array<{
    icon: LucideIcon
    title: string
    warning?: boolean
    body: React.ReactNode
  }> = [
    {
      icon: FileText,
      title: "What we agreed",
      body: (
        <List
          items={brief.agreed.map((row) => row.text)}
          empty="Nothing was recorded as agreed at the last visit."
        />
      ),
    },
    {
      icon: CheckCircle2,
      title: "What I did",
      body:
        brief.did.length === 0 ? (
          <Empty>No check-in recorded whether any of it happened.</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {brief.did.map((row, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                {/* The status is stated plainly and never softened —
                    a gap is the signal the doctor needs. */}
                <span
                  className={cn(
                    "mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium",
                    STATUS_TONE[row.status] ?? "bg-muted text-muted-foreground",
                  )}
                >
                  {STATUS_LABEL[row.status] ?? row.status}
                </span>
                <span className="leading-snug">{row.text}</span>
              </li>
            ))}
          </ul>
        ),
    },
    {
      icon: CircleDashed,
      title: "What happened",
      body:
        brief.happened.length === 0 ? (
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
        ),
    },
    {
      icon: TrendingUp,
      title: "What changed",
      body:
        brief.changed.length === 0 ? (
          <Empty>No change was recorded either way.</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {brief.changed.map((row, i) => (
              <li key={i} className="text-sm leading-snug">
                <span
                  aria-hidden
                  className={cn(
                    "mr-1.5 inline-block size-2 rounded-full",
                    DIRECTION_DOT[row.direction] ?? "bg-muted-foreground",
                  )}
                />
                {row.text}
              </li>
            ))}
          </ul>
        ),
    },
    ...(brief.open_questions.length > 0
      ? [
          {
            icon: HelpCircle,
            title: "Questions for the doctor",
            body: <List items={brief.open_questions} empty="" />,
          },
        ]
      : []),
    // Tinted rather than blended in, deliberately. A doctor reading this takes
    // absence as "nothing to report", so what the record does not cover has to
    // stay the loudest thing on the page.
    ...(brief.gaps.length > 0
      ? [
          {
            icon: AlertCircle,
            title: "What this record does not cover",
            warning: true,
            body: <List items={brief.gaps} empty="" />,
          },
        ]
      : []),
  ]

  return (
    <article className="rounded-3xl border border-border bg-card p-5 shadow-md print:rounded-none print:border-none print:shadow-none">
      <h2 className="font-[family-name:var(--font-display)] text-2xl font-medium tracking-tight text-foreground">
        Next-visit brief
      </h2>
      {meta && <p className="mt-1.5 text-xs text-muted-foreground">{meta}</p>}

      <div className="mt-4 divide-y divide-border border-t-2 border-primary">
        {sections.map((section, i) => (
          <section
            key={section.title}
            className={cn("py-4", i === 0 && "pt-3")}
            style={reveal(animate, i)}
          >
            {section.warning ? (
              <div className="rounded-xl bg-warning/10 p-3">
                <SectionHead
                  icon={section.icon}
                  title={section.title}
                  warning
                />
                <div className="text-sm leading-relaxed text-warning-foreground">
                  {section.body}
                </div>
              </div>
            ) : (
              <>
                <SectionHead icon={section.icon} title={section.title} />
                <div className="text-sm leading-relaxed text-foreground">
                  {section.body}
                </div>
              </>
            )}
          </section>
        ))}

        <footer
          className="pt-4 text-xs leading-relaxed text-muted-foreground"
          style={reveal(animate, sections.length)}
        >
          Prepared by the patient from recorded consultations and self-reported
          check-ins. Not a medical record and not a clinical assessment.
        </footer>
      </div>
    </article>
  )
}

function SectionHead({
  icon: Icon,
  title,
  warning,
}: {
  icon: LucideIcon
  title: string
  warning?: boolean
}) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <Icon
        className={cn(
          "size-4 shrink-0",
          warning ? "text-warning-foreground" : "text-primary",
        )}
      />
      <h3
        className={cn(
          "text-sm font-semibold",
          warning ? "text-warning-foreground" : "text-foreground",
        )}
      >
        {title}
      </h3>
    </div>
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
