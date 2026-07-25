"use client"

import Link from "next/link"
import {
  CalendarDays,
  CalendarClock,
  ChevronRight,
  MapPin,
  Stethoscope,
  Link2Off,
} from "lucide-react"
import type { Appointment, AppData } from "@/lib/types"
import { conditionName, isUpcoming, untilLabel } from "@/lib/store"
import { formatDate } from "@/lib/dates"

export function ConsultationCard({
  appointment,
  data,
  showCondition = true,
}: {
  appointment: Appointment
  data: AppData
  showCondition?: boolean
}) {
  const linked = conditionName(data, appointment.conditionId)
  const upcoming = isUpcoming(appointment)
  // "Not processed yet" describes a failure to summarise. For an appointment
  // that has not happened there is nothing to summarise, and saying so where
  // the diagnosis goes reads as something gone wrong.
  const diagnosis = upcoming
    ? appointment.doctorName || "Upcoming appointment"
    : appointment.summary?.doctor_diagnosis?.trim() ||
      (appointment.transcript ? "Summary not generated yet" : "Not processed yet")

  return (
    <Link
      href={`/consultation/${appointment.id}`}
      className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/40"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="size-3.5" />
            {formatDate(appointment.date)}
          </span>
          {upcoming && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 font-medium text-primary">
              <CalendarClock className="size-3" />
              {untilLabel(appointment.date)}
            </span>
          )}
          <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 font-medium text-secondary-foreground">
            <MapPin className="size-3" />
            {appointment.careSetting}
          </span>
        </div>
        <p className="mt-1.5 line-clamp-1 text-sm font-medium text-foreground">
          {diagnosis}
        </p>
        {showCondition && (
          <p className="mt-1 inline-flex items-center gap-1 text-xs">
            {linked ? (
              <>
                <Stethoscope className="size-3 text-primary" />
                <span className="text-primary">{linked}</span>
              </>
            ) : (
              <>
                <Link2Off className="size-3 text-muted-foreground" />
                <span className="text-muted-foreground">Not linked to a condition</span>
              </>
            )}
          </p>
        )}
      </div>
      <ChevronRight className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}
