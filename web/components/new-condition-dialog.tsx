"use client"

import * as React from "react"
import { useApp } from "@/lib/store"
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

export function NewConditionDialog({
  trigger,
  onCreated,
}: {
  trigger: React.ReactNode
  onCreated?: (id: string) => void
}) {
  const { addCondition } = useApp()
  const [open, setOpen] = React.useState(false)
  const [name, setName] = React.useState("")

  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed || saving) return
    setSaving(true)
    setError(null)
    try {
      // The condition is created on the server, so this awaits a round trip
      // rather than closing optimistically — the id it returns is what every
      // later call for this interval is keyed to.
      const condition = await addCondition(trimmed)
      setName("")
      setOpen(false)
      onCreated?.(condition.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create it.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New condition</DialogTitle>
          <DialogDescription>
            Group appointments by what you&apos;re being treated for, e.g. &ldquo;Kidney
            Failure&rdquo; or &ldquo;Fractured Arm&rdquo;.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Label htmlFor="condition-name">Condition name</Label>
          <Input
            id="condition-name"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.nativeEvent.isComposing &&
                e.keyCode !== 229
              ) {
                e.preventDefault()
                handleCreate()
              }
            }}
            placeholder="e.g. Kidney Failure"
            className="h-11"
          />
        </div>
        {error && <p className="text-sm text-warning-foreground">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={!name.trim() || saving}>
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
