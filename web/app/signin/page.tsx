"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Loader2 } from "lucide-react"
import { ApiError } from "@/lib/api"
import { useApp } from "@/lib/store"
import { AppShell, Content } from "@/components/app-shell"
import { Wordmark } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function SignInPage() {
  const router = useRouter()
  const { data, hydrated, signIn } = useApp()
  const [name, setName] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (hydrated && data.profile) {
      router.replace(data.consent ? "/home" : "/consent")
    }
  }, [hydrated, data.profile, data.consent, router])

  const canSubmit = name.trim().length > 0 && password.length > 0

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await signIn({ name: name.trim(), password })
      router.replace("/consent")
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not sign in. Please try again.",
      )
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <Content className="flex flex-1 flex-col justify-center">
        <div className="mb-8">
          <Wordmark iconSize={32} className="[&_span]:text-xl" />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-balance">
            Welcome back
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">
            Sign in to pick up your record right where you left it.
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
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="h-11"
            />
          </div>

          {error && (
            <p className="rounded-xl bg-destructive/10 px-3 py-2.5 text-xs leading-relaxed text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" className="mt-1 h-12" disabled={!canSubmit || submitting}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Sign in
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            New here?{" "}
            <Link href="/onboarding" className="font-medium text-primary">
              Create an account
            </Link>
          </p>
        </form>
      </Content>
    </AppShell>
  )
}
