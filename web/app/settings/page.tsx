"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ShieldCheck, Bell, Trash2, FileText } from "lucide-react"
import { useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { PrivacyNotice } from "@/components/privacy-notice"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
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
  const { data, hydrated, setReminders, clearAll } = useApp()

  React.useEffect(() => {
    if (!hydrated) return
    if (!data.profile || !data.consent) router.replace("/onboarding")
  }, [hydrated, data.profile, data.consent, router])

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
      <ScreenHeader title="Settings & privacy" backHref="/" />

      <Content className="flex flex-col gap-6 pb-10">
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-muted-foreground">Your profile</h2>
          <div className="rounded-2xl border border-border bg-card p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Name</span>
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
          <PrivacyNotice />
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
                <li>You can withdraw consent and erase everything at any time.</li>
              </ul>
            </DialogContent>
          </Dialog>
        </section>

        <section className="flex flex-col gap-3 border-t border-border pt-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
            <Trash2 className="size-4" />
            Withdraw & erase
          </h2>
          <p className="text-sm text-muted-foreground text-pretty">
            Withdrawing consent removes all health data stored on this device.
          </p>
          <Dialog>
            <DialogTrigger
              render={
                <Button variant="destructive" className="self-start">
                  Withdraw consent & delete my data
                </Button>
              }
            />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Withdraw consent and erase everything?</DialogTitle>
                <DialogDescription>
                  This permanently deletes your profile, conditions, appointments,
                  summaries, and reminders from this device. This cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end">
                <Button
                  variant="destructive"
                  onClick={() => {
                    clearAll()
                    router.replace("/onboarding")
                  }}
                >
                  Erase everything
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </section>
      </Content>
    </AppShell>
  )
}
