"use client"

import * as React from "react"
import { CalendarPlus } from "lucide-react"
import { useApp } from "@/lib/store"
import type { Appointment } from "@/lib/types"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function defaultReminderDate(raw: string): string {
  const parsed = new Date(raw)
  if (!Number.isNaN(parsed.getTime()) && /\d{4}-\d{2}-\d{2}/.test(raw)) {
    return raw.slice(0, 10)
  }
  const d = new Date()
  d.setDate(d.getDate() + 14)
  return d.toISOString().slice(0, 10)
}

export function AddReminderDialog({ appointment }: { appointment: Appointment }) {
  const { addReminder, data } = useApp()
  const plan = appointment.summary?.future_plan
  const [open, setOpen] = React.useState(false)
  const [date, setDate] = React.useState(defaultReminderDate(plan?.date_or_timeframe ?? ""))
  const [purpose, setPurpose] = React.useState(plan?.purpose ?? "Follow-up")

  const existing = data.reminders.find((r) => r.appointmentId === appointment.id)

  function handleAdd() {
    if (!date) return
    addReminder({
      conditionId: appointment.conditionId,
      appointmentId: appointment.id,
      date,
      purpose: purpose.trim() || "Follow-up",
    })
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant={existing ? "outline" : "default"} size="sm">
            <CalendarPlus className="size-4" />
            {existing ? "Update reminder" : "Add reminder"}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Follow-up reminder</DialogTitle>
          <DialogDescription>
            We&apos;ll show this on your Home screen. Reminders appear only when
            they&apos;re turned on in Settings.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="reminder-date">Date</Label>
            <Input
              id="reminder-date"
              type="date"
              value={date}
              min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDate(e.target.value)}
              className="h-11"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="reminder-purpose">Purpose</Label>
            <Input
              id="reminder-purpose"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="e.g. Blood test review"
              className="h-11"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={!date}>
            Save reminder
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
