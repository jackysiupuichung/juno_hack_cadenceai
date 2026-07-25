"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ShieldCheck } from "lucide-react"
import { useApp } from "@/lib/store"
import { AppShell, Content } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { PrivacyNotice } from "@/components/privacy-notice"

export default function ConsentPage() {
  const router = useRouter()
  const { data, hydrated, saveConsent } = useApp()
  const [terms, setTerms] = React.useState(false)
  const [health, setHealth] = React.useState(false)

  React.useEffect(() => {
    if (hydrated && !data.profile) router.replace("/onboarding")
    else if (hydrated && data.consent) router.replace("/home")
  }, [hydrated, data.profile, data.consent, router])

  const canContinue = terms && health

  function handleContinue() {
    if (!canContinue) return
    saveConsent({
      termsAccepted: terms,
      healthDataProcessing: health,
      timestamp: new Date().toISOString(),
    })
    router.replace("/home")
  }

  return (
    <AppShell>
      <Content className="flex flex-col gap-6 pb-8">
        <div>
          <div className="flex size-12 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
            <ShieldCheck className="size-6" />
          </div>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-balance">
            Your privacy
          </h1>
        </div>

        <PrivacyNotice />

        <div className="flex flex-col gap-3">
          <label
            htmlFor="terms"
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4"
          >
            <Checkbox
              id="terms"
              checked={terms}
              onCheckedChange={(v) => setTerms(v === true)}
              className="mt-0.5"
            />
            <span className="text-sm leading-relaxed">
              I agree to the Terms &amp; Conditions and have read the Privacy
              Notice.
            </span>
          </label>

          <label
            htmlFor="health"
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4"
          >
            <Checkbox
              id="health"
              checked={health}
              onCheckedChange={(v) => setHealth(v === true)}
              className="mt-0.5"
            />
            <span className="text-sm leading-relaxed">
              I consent to my consultations being recorded and my health data being
              processed as described in the Privacy Notice.
            </span>
          </label>
        </div>

        <Button
          size="lg"
          className="h-12"
          disabled={!canContinue}
          onClick={handleContinue}
        >
          Continue
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          You can withdraw consent or delete all your data at any time in Settings.
        </p>
      </Content>
    </AppShell>
  )
}
