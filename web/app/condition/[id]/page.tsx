"use client"

import * as React from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import {
  Mic,
  Link2,
  CheckCircle2,
  RotateCcw,
  Trash2,
  Pencil,
  ChevronRight,
  CalendarDays,
  CalendarClock,
  MapPin,
  FileText,
} from "lucide-react"
import { appointmentsForCondition, isUpcoming, untilLabel, useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { StatusBadge } from "@/components/status-badge"
import { LinkConsultationDialog } from "@/components/link-consultation-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export default function ConditionDetailPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const {
    data,
    hydrated,
    completeCondition,
    reopenCondition,
    deleteCondition,
    renameCondition,
  } = useApp()

  const condition = data.conditions.find((c) => c.id === params.id)

  React.useEffect(() => {
    if (hydrated && !condition) router.replace("/home")
  }, [hydrated, condition, router])

  const [renameOpen, setRenameOpen] = React.useState(false)
  const [nameDraft, setNameDraft] = React.useState("")
  const [renameError, setRenameError] = React.useState<string | null>(null)
  const [renaming, setRenaming] = React.useState(false)

  async function handleRename() {
    if (!condition) return
    const trimmed = nameDraft.trim()
    if (!trimmed) {
      setRenameError("Name can't be empty.")
      return
    }
    setRenaming(true)
    setRenameError(null)
    try {
      await renameCondition(condition.id, trimmed)
      setRenameOpen(false)
    } catch (err) {
      setRenameError(err instanceof Error ? err.message : "Couldn't rename it.")
    } finally {
      setRenaming(false)
    }
  }

  if (!condition) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const allAppts = appointmentsForCondition(data, condition.id)
  // An appointment ahead is not a consultation. Listing it among them puts a
  // row reading "Not processed yet" above every visit that actually happened —
  // which describes a failure, when the truth is that it has not happened.
  const upcoming = allAppts.filter(isUpcoming)
  const appts = allAppts.filter((a) => !isUpcoming(a))
  const nextAppt = upcoming[upcoming.length - 1] // soonest, since sorted newest-first
  const isCompleted = condition.status === "completed"

  return (
    <AppShell>
      <ScreenHeader
        title={condition.name}
        backHref="/home"
        right={
          <div className="flex items-center gap-1">
            {!isCompleted && (
              <Button
                variant="ghost"
                size="icon"
                aria-label="Rename condition"
                onClick={() => {
                  setNameDraft(condition.name)
                  setRenameError(null)
                  setRenameOpen(true)
                }}
              >
                <Pencil className="size-4" />
              </Button>
            )}
            <StatusBadge status={condition.status} />
          </div>
        }
      />

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename condition</DialogTitle>
            <DialogDescription>
              This changes what you see it called — it doesn&apos;t affect the
              consultations or plan linked to it.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            placeholder="e.g. Thyroid"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleRename()
            }}
          />
          {renameError && (
            <p className="text-sm text-destructive">{renameError}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRenameOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleRename()} disabled={renaming}>
              {renaming ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Content className="flex flex-col gap-5 pb-28">
        {isCompleted && (
          <div className="rounded-xl bg-muted px-4 py-3 text-sm text-muted-foreground">
            This condition is marked as completed and is read-only.
          </div>
        )}

        {/* The appointment ahead, and directly beneath it the brief to carry
            into it. Together they are the product's whole claim: the interval
            has an end, and the patient walks into it with an account of it
            rather than from a cold start. */}
        {nextAppt && (
          <section className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary">
                <CalendarClock className="size-3.5" />
                {untilLabel(nextAppt.date)}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatDate(nextAppt.date)}
              </span>
            </div>
            {nextAppt.doctorName && (
              <p className="mt-2 text-sm font-medium text-foreground">
                {nextAppt.doctorName}
              </p>
            )}
            {nextAppt.organisationName && (
              <p className="mt-0.5 inline-flex items-start gap-1 text-xs text-muted-foreground">
                <MapPin className="mt-0.5 size-3 shrink-0" />
                <span>{nextAppt.organisationName}</span>
              </p>
            )}
          </section>
        )}

        {/* The hero. Placed above the consultation list rather than below it
            because the brief is what the patient came for on the day of an
            appointment, and burying it under a scroll makes it the thing they
            forget to bring. */}
        {appts.length > 0 && (
          <Button
            size="lg"
            className="w-full"
            nativeButton={false}
            render={<Link href={`/condition/${condition.id}/brief`} />}
          >
            <FileText className="size-4" />
            {nextAppt ? "Brief for this appointment" : "Next-visit brief"}
          </Button>
        )}

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-muted-foreground">
              Consultations
            </h2>
            {!isCompleted && (
              <LinkConsultationDialog
                conditionId={condition.id}
                trigger={
                  <Button size="sm" variant="ghost">
                    <Link2 className="size-4" />
                    Link existing
                  </Button>
                }
              />
            )}
          </div>

          {appts.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center">
              <p className="font-medium">No consultations yet</p>
              <p className="mt-1 text-sm text-muted-foreground text-pretty">
                Record a consultation for this condition, or link one you&apos;ve
                already recorded.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {appts.map((a) => {
                const diagnosis =
                  a.summary?.doctor_diagnosis?.trim() ||
                  (a.transcript ? "Summary not generated yet" : "Not processed yet")
                return (
                  <Link
                    key={a.id}
                    href={`/consultation/${a.id}`}
                    className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/40"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <CalendarDays className="size-3.5" />
                          {formatDate(a.date)}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 font-medium text-secondary-foreground">
                          <MapPin className="size-3" />
                          {a.careSetting}
                        </span>
                      </div>
                      <p className="mt-1.5 line-clamp-1 text-sm font-medium text-foreground">
                        {diagnosis}
                      </p>
                    </div>
                    <ChevronRight className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                  </Link>
                )
              })}
            </div>
          )}
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-5">
          {isCompleted ? (
            <Button
              variant="outline"
              size="lg"
              onClick={() => reopenCondition(condition.id)}
            >
              <RotateCcw className="size-4" />
              Reopen condition
            </Button>
          ) : (
            <Button
              variant="outline"
              size="lg"
              onClick={() => completeCondition(condition.id)}
            >
              <CheckCircle2 className="size-4" />
              Mark treatment completed
            </Button>
          )}

          <Dialog>
            <DialogTrigger
              render={
                <Button variant="destructive" size="lg">
                  <Trash2 className="size-4" />
                  Delete condition
                </Button>
              }
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete this condition?</DialogTitle>
                <DialogDescription>
                  This removes &ldquo;{condition.name}&rdquo;. Its consultations are
                  kept and simply unlinked — you&apos;ll still find them in the
                  Consultations tab. This cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end">
                <Button
                  variant="destructive"
                  onClick={() => {
                    deleteCondition(condition.id)
                    router.replace("/home")
                  }}
                >
                  Delete permanently
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </section>
      </Content>

      {!isCompleted && (
        <div className="sticky bottom-0 z-20 border-t border-border bg-background/90 px-4 py-3 backdrop-blur-md">
          <Button
            size="lg"
            className="h-12 w-full"
            nativeButton={false}
            render={<Link href={`/consultation/new?condition=${condition.id}`} />}
          >
            <Mic className="size-4" />
            New consultation
          </Button>
        </div>
      )}
    </AppShell>
  )
}
