"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Loader2, ShieldAlert } from "lucide-react"
import { ApiError } from "@/lib/api"
import { useApp } from "@/lib/store"
import { computeAge } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { Wordmark } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function OnboardingPage() {
  const router = useRouter()
  const { data, hydrated, signUp } = useApp()
  const [name, setName] = React.useState("")
  const [dob, setDob] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [blocked, setBlocked] = React.useState(false)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (hydrated && data.profile) {
      router.replace(data.consent ? "/home" : "/consent")
    }
  }, [hydrated, data.profile, data.consent, router])

  const age = computeAge(dob)
  const canSubmit = name.trim().length > 0 && age !== null && password.length >= 8

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit || age === null || submitting) return
    if (age < 18) {
      setBlocked(true)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await signUp({ name: name.trim(), password, dateOfBirth: dob })
      router.replace("/consent")
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not create your account. Please try again.",
      )
      setSubmitting(false)
    }
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
      <ScreenHeader title="" backHref="/" />
      <Content className="flex flex-1 flex-col justify-center">
        <div className="mb-8">
          <Wordmark iconSize={32} className="[&_span]:text-xl" />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-balance">
            Create your account
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">
            Your record follows this account, not this device, so it&apos;s
            here whenever you sign back in.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Username</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. alexmorgan"
              autoComplete="username"
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
              <p
                className={
                  age < 18
                    ? "text-xs text-warning-foreground"
                    : "text-xs text-muted-foreground"
                }
              >
                {age < 18
                  ? "We only ask for the minimum needed to personalise your summaries. This app is for adults aged 18 or over."
                  : `You are ${age} year${age === 1 ? "" : "s"} old.`}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
              className="h-11"
            />
            {password.length > 0 && password.length < 8 && (
              <p className="text-xs text-warning-foreground">
                Password must be at least 8 characters.
              </p>
            )}
          </div>

          {error && (
            <p className="rounded-xl bg-destructive/10 px-3 py-2.5 text-xs leading-relaxed text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" className="mt-1 h-12" disabled={!canSubmit || submitting}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Create account
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/signin" className="font-medium text-primary">
              Sign in
            </Link>
          </p>
        </form>
      </Content>
    </AppShell>
  )
}
