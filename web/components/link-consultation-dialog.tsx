"use client"

import * as React from "react"
import { Link2, Check, CalendarDays, Stethoscope } from "lucide-react"
import { useApp, conditionName } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

export function LinkConsultationDialog({
  conditionId,
  trigger,
}: {
  conditionId: string
  trigger: React.ReactNode
}) {
  const { data, linkAppointment } = useApp()
  const [open, setOpen] = React.useState(false)

  // Candidates: any consultation not already linked to THIS condition.
  const candidates = data.appointments
    .filter((a) => a.conditionId !== conditionId)
    .sort((a, b) => (a.date < b.date ? 1 : -1))

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Link an existing consultation</DialogTitle>
          <DialogDescription>
            Attach a consultation you&apos;ve already recorded to this condition.
          </DialogDescription>
        </DialogHeader>

        {candidates.length === 0 ? (
          <p className="rounded-xl bg-muted/60 px-4 py-6 text-center text-sm text-muted-foreground">
            No other consultations to link. Record one from the Consultations tab
            first.
          </p>
        ) : (
          <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto">
            {candidates.map((a) => {
              const otherCondition = conditionName(data, a.conditionId)
              const diagnosis =
                a.summary?.doctor_diagnosis?.trim() ||
                (a.transcript ? "Summary not generated yet" : "Not processed yet")
              return (
                <li
                  key={a.id}
                  className="flex items-center gap-3 rounded-xl border border-border bg-card p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="size-3.5" />
                        {formatDate(a.date)}
                      </span>
                      <span className="rounded-full bg-secondary px-2 py-0.5 font-medium text-secondary-foreground">
                        {a.careSetting}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-1 text-sm font-medium text-foreground">
                      {diagnosis}
                    </p>
                    {otherCondition && (
                      <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                        <Stethoscope className="size-3" />
                        Currently: {otherCondition}
                      </p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => linkAppointment(a.id, conditionId)}
                  >
                    <Link2 className="size-4" />
                    Link
                  </Button>
                </li>
              )
            })}
          </ul>
        )}

        <div className="flex justify-end">
          <Button onClick={() => setOpen(false)}>
            <Check className="size-4" />
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
