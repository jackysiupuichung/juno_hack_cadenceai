"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { HeartPulse, ShieldAlert } from "lucide-react"
import { useApp } from "@/lib/store"
import { computeAge } from "@/lib/dates"
import { AppShell, Content } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function OnboardingPage() {
  const router = useRouter()
  const { data, hydrated, saveProfile } = useApp()
  const [name, setName] = React.useState("")
  const [dob, setDob] = React.useState("")
  const [blocked, setBlocked] = React.useState(false)

  React.useEffect(() => {
    if (hydrated && data.profile) {
      router.replace(data.consent ? "/" : "/consent")
    }
  }, [hydrated, data.profile, data.consent, router])

  const age = computeAge(dob)
  const canSubmit = name.trim().length > 0 && age !== null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit || age === null) return
    if (age < 18) {
      setBlocked(true)
      return
    }
    saveProfile({ name: name.trim(), dateOfBirth: dob })
    router.replace("/consent")
  }

  if (blocked) {
    return (
      <AppShell>
        <Content className="flex flex-1 flex-col items-center justify-center text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-warning/15 text-warning-foreground">
            <ShieldAlert className="size-8" />
          </div>
          <h1 className="mt-6 text-xl font-semibold text-balance">
            You must be 18 or over to use this app
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground text-pretty">
            This app records medical consultations and processes sensitive health
            information, and is only available to adults. If you&apos;re under 18,
            please ask a parent, guardian, or your clinician about your appointment
            instead.
          </p>
          <p className="mt-6 text-xs text-muted-foreground">
            None of your details have been saved.
          </p>
          <Button
            variant="outline"
            className="mt-6"
            size="lg"
            onClick={() => {
              setBlocked(false)
              setDob("")
            }}
          >
            Go back
          </Button>
        </Content>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <Content className="flex flex-1 flex-col justify-center">
        <div className="mb-8">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
            <HeartPulse className="size-6" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-balance">
            Welcome to Cadence
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">
            Record your doctor appointments and turn them into clear, easy-to-read
            summaries. Let&apos;s set up your profile.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Your name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alex Morgan"
              autoComplete="name"
              className="h-11"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="dob">Date of birth</Label>
            <Input
              id="dob"
              type="date"
              value={dob}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDob(e.target.value)}
              className="h-11"
            />
            {age !== null && (
              <p className="text-xs text-muted-foreground">
                You are {age} year{age === 1 ? "" : "s"} old.
              </p>
            )}
          </div>

          <p className="rounded-xl bg-muted px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
            We only ask for the minimum needed to personalise your summaries. This
            app is for adults aged 18 or over.
          </p>

          <Button type="submit" size="lg" className="mt-1 h-12" disabled={!canSubmit}>
            Continue
          </Button>
        </form>
      </Content>
    </AppShell>
  )
}
