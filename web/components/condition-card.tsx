"use client"

import Link from "next/link"
import { ChevronRight, CalendarClock, FileText } from "lucide-react"
import type { AppData, Condition } from "@/lib/types"
import { appointmentsForCondition, isUpcoming, untilLabel } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { StatusBadge } from "@/components/status-badge"

export function ConditionCard({
  condition,
  data,
}: {
  condition: Condition
  data: AppData
}) {
  const allAppts = appointmentsForCondition(data, condition.id)
  // The count is of consultations that happened. Including one still in the
  // diary overstates the record by one and makes the number disagree with the
  // list on the condition screen.
  const appts = allAppts.filter((a) => !isUpcoming(a))
  const nextAppt = allAppts.filter(isUpcoming).at(-1)
  const reminders = data.reminders
    .filter((r) => r.conditionId === condition.id)
    .sort((a, b) => a.date.localeCompare(b.date))
  const nextReminder = reminders.find((r) => r.date >= new Date().toISOString().slice(0, 10))

  return (
    <Link
      href={`/condition/${condition.id}`}
      className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/40 active:bg-muted/60"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="truncate text-base font-semibold">{condition.name}</h3>
          <StatusBadge status={condition.status} />
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <FileText className="size-3.5" />
            {appts.length} consultation{appts.length === 1 ? "" : "s"}
          </span>
          {/* A booked appointment outranks a reminder derived from a summary's
              follow-up timeframe: one is a date the patient has, the other is
              a date they were told to arrange. */}
          {nextAppt ? (
            <span className="inline-flex items-center gap-1 font-medium text-primary">
              <CalendarClock className="size-3.5" />
              {untilLabel(nextAppt.date)} · {formatDate(nextAppt.date)}
            </span>
          ) : (
            nextReminder && (
              <span className="inline-flex items-center gap-1 text-primary">
                <CalendarClock className="size-3.5" />
                Next {formatDate(nextReminder.date)}
              </span>
            )
          )}
        </div>
      </div>
      <ChevronRight className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}
