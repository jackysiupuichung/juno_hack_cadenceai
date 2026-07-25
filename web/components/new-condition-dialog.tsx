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

  function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed) return
    const condition = addCondition(trimmed)
    setName("")
    setOpen(false)
    onCreated?.(condition.id)
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
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={!name.trim()}>
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
