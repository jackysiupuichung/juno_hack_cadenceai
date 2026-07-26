"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  ShieldCheck,
  ShieldOff,
  Bell,
  Trash2,
  FileText,
  LogOut,
  Loader2,
  ChevronDown,
} from "lucide-react"
import { useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { cn } from "@/lib/utils"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { PrivacyNotice } from "@/components/privacy-notice"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export default function SettingsPage() {
  const router = useRouter()
  const { data, hydrated, setReminders, logOut, withdrawConsent, deleteAllData } = useApp()
  const [deleting, setDeleting] = React.useState(false)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)
  const [showConsentDetail, setShowConsentDetail] = React.useState(false)
  // Log out and withdraw-consent each clear a field this guard watches, then
  // navigate somewhere other than /onboarding themselves. Without this, the
  // guard's own redirect can fire in the same render pass and win the race,
  // overriding the destination the button actually asked for.
  const skipGuardRef = React.useRef(false)

  React.useEffect(() => {
    if (!hydrated) return
    if (skipGuardRef.current) return
    if (!data.profile || !data.consent) router.replace("/onboarding")
  }, [hydrated, data.profile, data.consent, router])

  async function handleDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteAllData()
      router.replace("/onboarding")
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : "Could not delete your data.",
      )
      setDeleting(false)
    }
  }

  if (!hydrated || !data.profile) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <ScreenHeader title="Settings & privacy" backHref="/home" />

      <Content className="flex flex-col gap-6 pb-10">
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-muted-foreground">Your profile</h2>
          <div className="rounded-2xl border border-border bg-card p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Username</span>
              <span className="font-medium text-foreground">{data.profile.name}</span>
            </div>
            <div className="mt-2 flex items-center justify-between border-t border-border pt-2">
              <span className="text-muted-foreground">Date of birth</span>
              <span className="font-medium text-foreground">
                {formatDate(data.profile.dateOfBirth)}
              </span>
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <Bell className="size-4" />
            Follow-up reminders
          </h2>
          <label
            htmlFor="reminders"
            className="flex cursor-pointer items-center justify-between rounded-2xl border border-border bg-card p-4"
          >
            <div className="pr-4">
              <p className="text-sm font-medium text-foreground">Show reminders</p>
              <p className="text-xs text-muted-foreground text-pretty">
                Display upcoming follow-ups on your home screen.
              </p>
            </div>
            <Switch
              id="reminders"
              checked={data.settings.remindersEnabled}
              onCheckedChange={(v) => setReminders(Boolean(v))}
            />
          </label>
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <ShieldCheck className="size-4" />
            Consent & data
          </h2>
          {data.consent && (
            <p className="text-sm text-muted-foreground">
              You consented to health-data processing on{" "}
              <span className="font-medium text-foreground">
                {formatDate(data.consent.timestamp)}
              </span>
              .
            </p>
          )}
          <button
            type="button"
            onClick={() => setShowConsentDetail((v) => !v)}
            className="flex items-center gap-1.5 self-start text-sm font-medium text-primary"
          >
            {showConsentDetail ? "Hide details" : "Show Consent & data"}
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform",
                showConsentDetail && "rotate-180",
              )}
            />
          </button>
          {showConsentDetail && <PrivacyNotice />}
          <Dialog>
            <DialogTrigger
              render={
                <Button variant="outline" size="sm" className="self-start">
                  <FileText className="size-4" />
                  How your data is handled
                </Button>
              }
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>How your data is handled</DialogTitle>
                <DialogDescription>
                  Plain-language summary of processing.
                </DialogDescription>
              </DialogHeader>
              <ul className="flex flex-col gap-2 text-sm text-foreground">
                <li>Recordings are transcribed and summarised, then the audio is discarded.</li>
                <li>Your profile, appointments, and summaries are stored only on this device.</li>
                <li>Health-data processing relies on the consent you provided.</li>
                <li>You can withdraw consent or delete everything at any time, below.</li>
              </ul>
            </DialogContent>
          </Dialog>
        </section>

        <section className="flex flex-col gap-3 border-t border-border pt-5">
          <h2 className="text-sm font-semibold text-muted-foreground">Account & data</h2>

          <div className="glass-subtle flex items-center justify-between gap-3 rounded-2xl p-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <LogOut className="size-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">Log out</p>
                <p className="truncate text-xs text-muted-foreground">
                  Sign out of this device. Your record is kept.
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => {
                skipGuardRef.current = true
                logOut()
                router.replace("/")
              }}
            >
              Log out
            </Button>
          </div>

          <div className="glass-subtle flex items-center justify-between gap-3 rounded-2xl p-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-warning/15 text-warning-foreground">
                <ShieldOff className="size-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">Withdraw consent</p>
                <p className="truncate text-xs text-muted-foreground">
                  Stop health-data processing. Nothing is deleted.
                </p>
              </div>
            </div>
            <Dialog>
              <DialogTrigger
                render={
                  <Button variant="outline" size="sm" className="shrink-0">
                    Withdraw
                  </Button>
                }
              />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Withdraw consent?</DialogTitle>
                  <DialogDescription>
                    Cadence will stop processing new health data. Your existing
                    profile, conditions, and consultations are kept, and you can
                    give consent again at any time. Nothing is deleted.
                  </DialogDescription>
                </DialogHeader>
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    onClick={() => {
                      skipGuardRef.current = true
                      withdrawConsent()
                      router.replace("/consent")
                    }}
                  >
                    Withdraw consent
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          <div className="glass-subtle flex items-center justify-between gap-3 rounded-2xl p-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
                <Trash2 className="size-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">Delete my data</p>
                <p className="truncate text-xs text-muted-foreground">
                  Permanently erase your entire record.
                </p>
              </div>
            </div>
            <Dialog>
              <DialogTrigger
                render={
                  <Button variant="destructive" size="sm" className="shrink-0">
                    Delete
                  </Button>
                }
              />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete everything?</DialogTitle>
                  <DialogDescription>
                    This permanently removes your profile, conditions,
                    consultations, summaries, and reminders. There is no way to
                    undo this.
                  </DialogDescription>
                </DialogHeader>
                {deleteError && (
                  <p className="text-sm text-destructive">{deleteError}</p>
                )}
                <div className="flex justify-end">
                  <Button
                    variant="destructive"
                    disabled={deleting}
                    onClick={handleDelete}
                  >
                    {deleting && <Loader2 className="size-4 animate-spin" />}
                    Delete everything
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </section>
      </Content>
    </AppShell>
  )
}
