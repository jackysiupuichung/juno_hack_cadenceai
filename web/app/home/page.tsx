"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Plus,
  Settings2,
  Bell,
  ChevronDown,
  ChevronRight,
  Stethoscope,
  Mic,
  CalendarDays,
} from "lucide-react"
import { allAppointments, useApp } from "@/lib/store"
import { formatShortDate } from "@/lib/dates"
import { AppShell, Content } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { ConditionCard } from "@/components/condition-card"
import { ConsultationCard } from "@/components/consultation-card"
import { NewConditionDialog } from "@/components/new-condition-dialog"
import { CheckInNotification } from "@/components/check-in-notification"
import { cn } from "@/lib/utils"

type Tab = "conditions" | "consultations"

export default function HomePage() {
  const router = useRouter()
  const { data, hydrated } = useApp()
  const [tab, setTab] = React.useState<Tab>("consultations")
  const [showCompleted, setShowCompleted] = React.useState(false)

  React.useEffect(() => {
    if (!hydrated) return
    if (!data.profile) router.replace("/onboarding")
    else if (!data.consent) router.replace("/consent")
  }, [hydrated, data.profile, data.consent, router])

  if (!hydrated || !data.profile || !data.consent) {
    return (
      <AppShell>
        <div role="status" className="flex flex-1 items-center justify-center">
          <span className="sr-only">Loading</span>
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  const active = data.conditions.filter((c) => c.status === "active")
  const completed = data.conditions.filter((c) => c.status === "completed")
  const consultations = allAppointments(data)
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = data.settings.remindersEnabled
    ? [...data.reminders]
        .filter((r) => r.date >= today)
        .sort((a, b) => a.date.localeCompare(b.date))
    : []

  const firstName = data.profile.name.split(" ")[0]

  return (
    <AppShell>
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-background/85 px-4 py-3 backdrop-blur-md">
        <div>
          <p className="text-xs text-muted-foreground">Welcome back</p>
          <h1 className="text-lg font-semibold leading-tight">{firstName}</h1>
        </div>
        <div className="flex items-center gap-1">
          {/* Calendar is reference material, so it lives up here; the badge
              keeps the "something is coming" signal it carried in the old
              bottom bar. */}
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            aria-label={
              upcoming.length > 0
                ? `My calendar, ${upcoming.length} upcoming`
                : "My calendar"
            }
            nativeButton={false}
            render={<Link href="/calendar" />}
          >
            <CalendarDays className="size-5" />
            {upcoming.length > 0 && (
              <span
                aria-hidden
                className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground"
              >
                {upcoming.length}
              </span>
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Settings"
            nativeButton={false}
            render={<Link href="/settings" />}
          >
            <Settings2 className="size-5" />
          </Button>
        </div>
      </header>

      <Content className="flex flex-col gap-5 pb-28">
        {/* Above everything else: a check-in that has to be hunted for is one
            that does not happen, and the interval is what this product is. */}
        {active.map((c) => (
          <CheckInNotification
            key={c.id}
            conditionId={c.id}
            conditionName={c.name}
          />
        ))}

        {upcoming.length > 0 && (
          <section className="flex flex-col gap-2">
            {upcoming.map((r) => {
              const condition = data.conditions.find((c) => c.id === r.conditionId)
              // A reminder is only worth surfacing if tapping it goes somewhere:
              // the brief is what the upcoming visit needs, so that's the target.
              const href = r.conditionId
                ? `/condition/${r.conditionId}/brief`
                : "/calendar"
              return (
                <Link
                  key={r.id}
                  href={href}
                  className="flex items-center gap-3 rounded-2xl border border-primary/25 bg-primary/5 p-3.5 transition-colors hover:bg-primary/10 active:bg-primary/15"
                >
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                    <Bell className="size-4.5" />
                  </div>
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-medium text-foreground">
                      Upcoming: {condition?.name ?? "Follow-up"}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {r.purpose || "Follow-up"} &middot; {formatShortDate(r.date)}
                    </p>
                    <p className="mt-0.5 text-xs font-medium text-primary">
                      {r.conditionId ? "View your brief" : "View in calendar"}
                    </p>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </Link>
              )
            })}
          </section>
        )}

        {/* Segmented view switch. Not marked up as tabs: real tabs need
            arrow-key focus and panel wiring, and claiming the role without
            them is worse for a screen reader than honest toggle buttons.
            Recording lives in the sticky bar, so only conditions keep a
            contextual add. */}
        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="View"
            className="grid flex-1 grid-cols-2 gap-1 rounded-2xl bg-muted p-1"
          >
            <TabButton
              active={tab === "consultations"}
              onClick={() => setTab("consultations")}
            >
              Consultations
            </TabButton>
            <TabButton
              active={tab === "conditions"}
              onClick={() => setTab("conditions")}
            >
              Conditions
            </TabButton>
          </div>
          {tab === "conditions" && (active.length > 0 || completed.length > 0) && (
            <NewConditionDialog
              onCreated={(id) => router.push(`/condition/${id}`)}
              trigger={
                <Button variant="secondary" size="icon" aria-label="New condition">
                  <Plus className="size-4.5" />
                </Button>
              }
            />
          )}
        </div>

        {tab === "consultations" ? (
          <section className="flex flex-col gap-3">
            {consultations.length === 0 ? (
              <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
                <div className="flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
                  <Mic className="size-7" />
                </div>
                <div>
                  <p className="font-medium">No consultations yet</p>
                  <p className="mt-1 text-sm text-muted-foreground text-pretty">
                    Record any appointment to get a clear summary. You don&apos;t
                    need to know your condition first.
                  </p>
                </div>
                <Button
                  size="lg"
                  nativeButton={false}
                  render={<Link href="/consultation/new" />}
                >
                  <Mic className="size-4" />
                  Record a consultation
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {consultations.map((a) => (
                  <ConsultationCard key={a.id} appointment={a} data={data} />
                ))}
              </div>
            )}
          </section>
        ) : (
          <>
            <section className="flex flex-col gap-3">
              {active.length === 0 && completed.length === 0 ? (
                <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-card px-6 py-12 text-center">
                  <div className="flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
                    <Stethoscope className="size-7" />
                  </div>
                  <div>
                    <p className="font-medium">No conditions yet</p>
                    <p className="mt-1 text-sm text-muted-foreground text-pretty">
                      Create a condition to group related consultations together.
                    </p>
                  </div>
                  <NewConditionDialog
                    onCreated={(id) => router.push(`/condition/${id}`)}
                    trigger={
                      <Button size="lg">
                        <Plus className="size-4" />
                        Add your first condition
                      </Button>
                    }
                  />
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {active.map((c) => (
                    <ConditionCard key={c.id} condition={c} data={data} />
                  ))}
                  {active.length === 0 && (
                    <p className="rounded-2xl border border-dashed border-border bg-card px-4 py-6 text-center text-sm text-muted-foreground">
                      No active conditions.
                    </p>
                  )}
                </div>
              )}
            </section>

            {completed.length > 0 && (
              <section>
                <button
                  type="button"
                  onClick={() => setShowCompleted((s) => !s)}
                  className="flex w-full items-center justify-between rounded-xl px-1 py-2 text-sm font-semibold text-muted-foreground"
                >
                  <span>Completed ({completed.length})</span>
                  <ChevronDown
                    className={cn(
                      "size-4 transition-transform",
                      showCompleted && "rotate-180",
                    )}
                  />
                </button>
                {showCompleted && (
                  <div className="mt-2 flex flex-col gap-3">
                    {completed.map((c) => (
                      <ConditionCard key={c.id} condition={c} data={data} />
                    ))}
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </Content>

      {/* The persistent slot under the thumb belongs to the loop's primary
          action — starting a capture — not to a read-only calendar. */}
      <div className="sticky bottom-0 z-20 border-t border-border bg-background/90 px-4 py-3 backdrop-blur-md">
        <Button
          size="lg"
          className="w-full"
          nativeButton={false}
          render={<Link href="/consultation/new" />}
        >
          <Mic className="size-4" />
          Record a consultation
        </Button>
      </div>
    </AppShell>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-xl px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}
