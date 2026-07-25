"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { Smile, Meh, Frown, AlertTriangle } from "lucide-react"
import { useApp } from "@/lib/store"
import { cn } from "@/lib/utils"
import type { CheckIn } from "@/lib/types"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

const OPTIONS: { value: CheckIn["feeling"]; label: string; icon: typeof Smile }[] = [
  { value: "better", label: "Better", icon: Smile },
  { value: "same", label: "About the same", icon: Meh },
  { value: "worse", label: "Worse", icon: Frown },
]

export default function CheckInPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { data, hydrated, setCheckIn } = useApp()

  const appointment = data.appointments.find((a) => a.id === params.id)
  const condition = appointment?.conditionId
    ? data.conditions.find((c) => c.id === appointment.conditionId)
    : undefined

  const [feeling, setFeeling] = React.useState<CheckIn["feeling"] | null>(
    appointment?.checkIn?.feeling ?? null,
  )
  const [note, setNote] = React.useState(appointment?.checkIn?.note ?? "")

  React.useEffect(() => {
    if (hydrated && !appointment) router.replace("/")
  }, [hydrated, appointment, router])

  if (!appointment) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const redFlags = appointment.summary?.red_flags ?? []

  function handleSave() {
    if (!feeling) return
    setCheckIn(appointment!.id, {
      feeling,
      note: note.trim() || undefined,
      date: new Date().toISOString(),
    })
    router.push(`/consultation/${appointment!.id}`)
  }

  return (
    <AppShell>
      <ScreenHeader
        title="Check-in"
        subtitle={condition ? condition.name : "Consultation"}
        backHref={`/consultation/${appointment.id}`}
      />

      <Content className="flex flex-col gap-5 pb-10">
        <div>
          <h1 className="text-balance text-xl font-semibold text-foreground">
            How are you feeling?
          </h1>
          <p className="mt-1 text-pretty text-sm text-muted-foreground">
            {condition
              ? `A quick check-in helps you track ${condition.name.toLowerCase()} since your last visit.`
              : "A quick check-in helps you track how you're doing since your last visit."}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-3">
          {OPTIONS.map((opt) => {
            const Icon = opt.icon
            const active = feeling === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setFeeling(opt.value)}
                aria-pressed={active}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-2xl border-2 bg-card p-4 text-center transition-colors",
                  active
                    ? "border-primary bg-primary/5 text-foreground"
                    : "border-border text-muted-foreground hover:border-primary/40",
                )}
              >
                <Icon
                  className={cn(
                    "size-7",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                />
                <span className="text-sm font-medium">{opt.label}</span>
              </button>
            )
          })}
        </div>

        {feeling === "worse" && redFlags.length > 0 && (
          <section className="rounded-2xl border border-warning/40 bg-warning/10 p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-warning-foreground">
              <AlertTriangle className="size-4" />
              Watch for these warning signs
            </h2>
            <ul className="mt-2 flex flex-col gap-1.5 text-sm text-foreground">
              {redFlags.map((flag, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-warning-foreground/70" />
                  <span>{flag}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-sm font-medium text-warning-foreground">
              If any of these apply, contact your doctor or seek urgent care.
            </p>
          </section>
        )}

        <div className="flex flex-col gap-2">
          <Label htmlFor="note">Anything you want to note? (optional)</Label>
          <Textarea
            id="note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Cough is easing but still tired in the mornings."
            rows={4}
          />
        </div>

        <Button
          size="lg"
          className="h-12 w-full"
          disabled={!feeling}
          onClick={handleSave}
        >
          Save check-in
        </Button>
      </Content>
    </AppShell>
  )
}
