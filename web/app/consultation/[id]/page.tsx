"use client"

import * as React from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import {
  AlertTriangle,
  Ban,
  CalendarClock,
  ClipboardList,
  HeartPulse,
  Leaf,
  MapPin,
  MessageCircleQuestion,
  Pill,
  Plus,
  Smile,
  Stethoscope,
  Trash2,
  User,
} from "lucide-react"
import { isUpcoming, untilLabel, useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { SummaryCard } from "@/components/summary-card"
import { AddReminderDialog } from "@/components/add-reminder-dialog"
import { NewConditionDialog } from "@/components/new-condition-dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

const NO_CONDITION = "none"

export default function ConsultationPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { data, synced, deleteAppointment, linkAppointment } = useApp()

  const appointment = data.appointments.find((a) => a.id === params.id)
  const condition = appointment?.conditionId
    ? data.conditions.find((c) => c.id === appointment.conditionId)
    : undefined
  const activeConditions = data.conditions.filter((c) => c.status === "active")

  React.useEffect(() => {
    // `synced`, not `hydrated` — a visit recorded elsewhere is missing from
    // this browser's cache until the server answers, and redirecting before
    // then drops the patient off a consultation that exists.
    if (synced && !appointment) router.replace("/home")
  }, [synced, appointment, router])

  if (!appointment) {
    return (
      <AppShell>
        <ScreenHeader title="Consultation" backHref="/home" />
        <div className="flex flex-1 items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const s = appointment.summary
  const plan = s?.future_plan
  const showFollowUp = Boolean(plan?.follow_up_needed)

  return (
    <AppShell>
      {/* Back to where this visit lives: its condition's timeline when it is
          linked, home when it is not. */}
      <ScreenHeader
        title="Consultation"
        subtitle={condition ? `${condition.name} · ${formatDate(appointment.date)}` : formatDate(appointment.date)}
        backHref={
          appointment.conditionId
            ? `/condition/${appointment.conditionId}`
            : "/home"
        }
      />

      <Content className="flex flex-col gap-4 pb-10">
        <section className="rounded-2xl border border-border bg-card p-4">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 font-medium text-secondary-foreground">
              <MapPin className="size-3.5" />
              {appointment.careSetting}
            </span>
            {appointment.organisationName && (
              <span className="text-muted-foreground">
                {appointment.organisationName}
              </span>
            )}
            {appointment.doctorName && (
              <span className="inline-flex items-center gap-1 text-muted-foreground">
                <User className="size-3.5" />
                {appointment.doctorName}
              </span>
            )}
          </div>
          {appointment.organisationAddress && (
            <p className="mt-1.5 text-xs text-muted-foreground">
              {appointment.organisationAddress}
            </p>
          )}
        </section>

        {/* Linked condition control */}
        <section className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-4">
          <Label htmlFor="linked-condition" className="flex items-center gap-1.5">
            <Stethoscope className="size-4 text-primary" />
            Linked condition
          </Label>
          <Select
            value={appointment.conditionId ?? NO_CONDITION}
            onValueChange={(v) =>
              linkAppointment(appointment.id, v === NO_CONDITION ? null : v)
            }
          >
            <SelectTrigger id="linked-condition" className="h-11 w-full">
              <SelectValue>
                {(value: string | null) =>
                  !value || value === NO_CONDITION
                    ? "Not linked"
                    : (activeConditions.find((c) => c.id === value)?.name ??
                      condition?.name ??
                      "Not linked")
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_CONDITION}>Not linked</SelectItem>
              {activeConditions.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground text-pretty">
            {condition
              ? "This consultation appears under the linked condition."
              : "Attach this consultation to a condition to keep related visits together."}
          </p>
          {/* Record-first must not dead-end: a visit recorded before its
              condition existed can mint one here and link itself to it. */}
          <NewConditionDialog
            onCreated={(id) => linkAppointment(appointment.id, id)}
            trigger={
              <Button
                variant="ghost"
                size="sm"
                className="self-start text-muted-foreground"
              >
                <Plus className="size-4" />
                New condition
              </Button>
            }
          />
        </section>

        {!s ? (
          <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center">
            {isUpcoming(appointment) ? (
              // Not a missing summary — an appointment that has not happened.
              // Saying "no summary was generated" here would report a failure
              // for a visit that is still in the diary.
              <>
                <p className="text-sm font-medium text-foreground">
                  {untilLabel(appointment.date)} · {formatDate(appointment.date)}
                </p>
                <p className="mt-1 text-sm text-muted-foreground text-pretty">
                  This appointment hasn&apos;t happened yet. Record it on the day
                  and the summary will appear here.
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                No summary was generated for this consultation.
              </p>
            )}
          </div>
        ) : (
          <>
            {s.doctor_diagnosis && (
              <SummaryCard icon={<Stethoscope />} title="Diagnosis">
                <p>{s.doctor_diagnosis}</p>
              </SummaryCard>
            )}

            {s.patient_symptoms_summary && (
              <SummaryCard icon={<ClipboardList />} title="What you described">
                <p>{s.patient_symptoms_summary}</p>
              </SummaryCard>
            )}

            {s.doctor_advice && (
              <SummaryCard icon={<HeartPulse />} title="Doctor's advice">
                <p>{s.doctor_advice}</p>
              </SummaryCard>
            )}

            {s.red_flags.length > 0 && (
              <SummaryCard
                tone="warning"
                icon={<AlertTriangle />}
                title="What to look out for — seek help if these happen"
              >
                <ul className="flex flex-col gap-1.5">
                  {s.red_flags.map((f, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-warning-foreground/70" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </SummaryCard>
            )}

            {s.medications.length > 0 && (
              <SummaryCard icon={<Pill />} title="Medications">
                <ul className="flex flex-col gap-3">
                  {s.medications.map((m, i) => (
                    <li key={i} className="rounded-xl bg-muted/60 p-3">
                      <p className="font-semibold text-foreground">
                        {m.name}
                        {m.dosage ? ` · ${m.dosage}` : ""}
                      </p>
                      <div className="mt-1 flex flex-col gap-0.5 text-muted-foreground">
                        {m.frequency && <span>How often: {m.frequency}</span>}
                        {m.duration && <span>Duration: {m.duration}</span>}
                        {m.instructions && <span>Notes: {m.instructions}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              </SummaryCard>
            )}

            {s.things_to_avoid.length > 0 && (
              <SummaryCard icon={<Ban />} title="Things to avoid">
                <ul className="flex flex-col gap-1.5">
                  {s.things_to_avoid.map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/60" />
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              </SummaryCard>
            )}

            {s.lifestyle_advice.length > 0 && (
              <SummaryCard icon={<Leaf />} title="Lifestyle advice">
                <ul className="flex flex-col gap-1.5">
                  {s.lifestyle_advice.map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/60" />
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              </SummaryCard>
            )}

            {showFollowUp && (
              <section className="rounded-2xl border border-primary/25 bg-primary/5 p-4">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <CalendarClock className="size-4 text-primary" />
                  Follow-up needed
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan?.purpose || "A follow-up was recommended."}
                  {plan?.date_or_timeframe ? ` (${plan.date_or_timeframe})` : ""}
                </p>
                <div className="mt-3">
                  <AddReminderDialog appointment={appointment} />
                </div>
              </section>
            )}
          </>
        )}

        {/* A check-in belongs to the interval, not to one appointment: it is
            answered against everything still open, and several of them
            accumulate across the weeks. So it hangs off the condition, and a
            consultation with no condition has no interval to check in on. */}
        <section className="flex flex-col gap-2 border-t border-border pt-4">
          {appointment.conditionId && (
            <Button
              variant="outline"
              size="lg"
              nativeButton={false}
              render={
                <Link href={`/condition/${appointment.conditionId}/check-in`} />
              }
            >
              <Smile className="size-4" />
              How has it gone since this visit?
            </Button>
          )}

          {/* Only when there is a summary to ask about: an unprocessed visit
              has no record behind the answers. */}
          {s && (
            <Button
              variant="outline"
              size="lg"
              nativeButton={false}
              render={<Link href={`/consultation/${appointment.id}/ask`} />}
            >
              <MessageCircleQuestion className="size-4" />
              Ask about this visit
            </Button>
          )}

          <Dialog>
            <DialogTrigger
              render={
                <Button variant="ghost" size="sm" className="text-muted-foreground">
                  <Trash2 className="size-4" />
                  Delete consultation
                </Button>
              }
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete this consultation?</DialogTitle>
                <DialogDescription>
                  This permanently removes the summary and any linked reminder. This
                  cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end">
                <Button
                  variant="destructive"
                  onClick={() => {
                    deleteAppointment(appointment.id)
                    router.replace("/home")
                  }}
                >
                  Delete
                </Button>
              </div>
            </DialogContent>
          </Dialog>

        </section>
      </Content>
    </AppShell>
  )
}
