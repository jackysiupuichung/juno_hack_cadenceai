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
  ChevronRight,
  CalendarDays,
  MapPin,
  FileText,
} from "lucide-react"
import { appointmentsForCondition, useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { StatusBadge } from "@/components/status-badge"
import { LinkConsultationDialog } from "@/components/link-consultation-dialog"
import { Button } from "@/components/ui/button"
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
  const { data, hydrated, completeCondition, reopenCondition, deleteCondition } =
    useApp()

  const condition = data.conditions.find((c) => c.id === params.id)

  React.useEffect(() => {
    if (hydrated && !condition) router.replace("/")
  }, [hydrated, condition, router])

  if (!condition) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const appts = appointmentsForCondition(data, condition.id)
  const isCompleted = condition.status === "completed"

  return (
    <AppShell>
      <ScreenHeader
        title={condition.name}
        backHref="/"
        right={<StatusBadge status={condition.status} />}
      />

      <Content className="flex flex-col gap-5 pb-28">
        {isCompleted && (
          <div className="rounded-xl bg-muted px-4 py-3 text-sm text-muted-foreground">
            This condition is marked as completed and is read-only.
          </div>
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
            Next-visit brief
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
                    router.replace("/")
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
