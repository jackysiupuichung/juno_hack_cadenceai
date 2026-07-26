"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Mic,
  FileText,
  MessageCircleHeart,
  ClipboardCheck,
  ArrowRight,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { useApp } from "@/lib/store"
import { Button } from "@/components/ui/button"
import { Reveal } from "@/components/reveal"
import { LoopSchematic } from "@/components/loop-schematic"

const LOOP_STEPS = [
  {
    icon: Mic,
    title: "Record the visit",
    body: "Capture the conversation with your doctor, start to finish. No notes to scribble, nothing to remember on the way out.",
  },
  {
    icon: FileText,
    title: "Understand it instantly",
    body: "A clear, plain-language summary — what was said, what it means, what you agreed to do next.",
  },
  {
    icon: MessageCircleHeart,
    title: "Follow through, by voice",
    body: "Short check-in calls over the following weeks track what actually happened — no forms, just a 30-second call.",
  },
  {
    icon: ClipboardCheck,
    title: "Walk into the next visit ready",
    body: "A brief that closes the loop: what you agreed, what you did, what changed. Hand it to your doctor and start at minute two.",
  },
]

const TRUST_POINTS = [
  {
    icon: ShieldCheck,
    title: "Yours, not the clinic's",
    body: "Your record lives with you and travels with you — to a specialist, a new city, a different doctor entirely.",
  },
  {
    icon: Sparkles,
    title: "Plain language, always",
    body: "No jargon dumps. Cadence explains what happened and what's next in words that make sense.",
  },
]

export default function LandingPage() {
  const router = useRouter()
  const { data, hydrated } = useApp()

  React.useEffect(() => {
    if (hydrated && data.profile && data.consent) router.replace("/home")
  }, [hydrated, data.profile, data.consent, router])

  return (
    <div className="min-h-dvh w-full bg-background">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-6">
        <Wordmark />
        <Button
          variant="ghost"
          size="sm"
          nativeButton={false}
          render={<Link href="/onboarding" />}
        >
          Sign in
        </Button>
      </header>

      {/* Hero */}
      <section className="relative mx-auto flex w-full max-w-5xl flex-col items-center px-6 pb-20 pt-10 text-center sm:pb-28 sm:pt-16">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-10 left-1/2 -z-10 h-[420px] w-[420px] -translate-x-1/2 rounded-full bg-primary/15 blur-3xl"
          style={{ animation: "orb-float 9s ease-in-out infinite" }}
        />

        <div
          className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-1.5 text-xs font-medium text-muted-foreground"
          style={{ animation: "fade-up 500ms var(--ease-out) both" }}
        >
          <span className="inline-flex size-1.5 rounded-full bg-primary" />
          Built for the patient, not the chart
        </div>

        <h1
          className="max-w-3xl text-balance font-[family-name:var(--font-display)] text-4xl font-medium leading-[1.08] tracking-tight text-foreground sm:text-6xl"
          style={{ animation: "fade-up 600ms var(--ease-out) 60ms both" }}
        >
          A visit isn&apos;t an event.
          <br />
          It&apos;s the start of an interval.
        </h1>

        <p
          className="mt-6 max-w-xl text-pretty text-lg text-muted-foreground"
          style={{ animation: "fade-up 600ms var(--ease-out) 120ms both" }}
        >
          Cadence captures what your doctor said, follows the plan through the
          weeks after, and walks you into the next visit already prepared.
        </p>

        <div
          className="mt-9 flex flex-col items-center gap-3 sm:flex-row"
          style={{ animation: "fade-up 600ms var(--ease-out) 180ms both" }}
        >
          <Button
            size="lg"
            className="h-12 px-7"
            nativeButton={false}
            render={<Link href="/onboarding" />}
          >
            Get started
            <ArrowRight className="size-4" />
          </Button>
          <Button
            size="lg"
            variant="ghost"
            className="h-12 px-7"
            nativeButton={false}
            render={<Link href="#how-it-works" />}
          >
            See how it works
          </Button>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto w-full max-w-5xl px-6 py-16 sm:py-24">
        <Reveal className="mx-auto max-w-xl text-center">
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-medium tracking-tight text-foreground sm:text-4xl">
            One loop, every visit
          </h2>
          <p className="mt-3 text-pretty text-muted-foreground">
            The same four steps, every time — until the record is something you
            can actually stand on.
          </p>
        </Reveal>

        <div className="relative mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div
            aria-hidden
            className="absolute left-0 right-0 top-9 hidden h-px bg-gradient-to-r from-transparent via-border to-transparent lg:block"
          />
          {LOOP_STEPS.map((step, i) => (
            <Reveal key={step.title} delay={i * 70}>
              <div className="relative flex flex-col items-center gap-3 text-center lg:items-start lg:text-left">
                <div className="relative z-10 flex size-14 shrink-0 items-center justify-center rounded-2xl bg-card text-primary ring-1 ring-border">
                  <step.icon className="size-6" />
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                    Step {i + 1}
                  </p>
                  <h3 className="mt-1 font-medium text-foreground">{step.title}</h3>
                  <p className="mt-1.5 text-pretty text-sm text-muted-foreground">
                    {step.body}
                  </p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={120}>
          <div className="mt-16">
            <LoopSchematic />
          </div>
        </Reveal>
      </section>

      {/* Trust */}
      <section className="mx-auto w-full max-w-5xl px-6 py-16 sm:py-24">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {TRUST_POINTS.map((point, i) => (
            <Reveal key={point.title} delay={i * 70}>
              <div className="flex h-full flex-col gap-3 rounded-3xl border border-border bg-card p-7">
                <div className="flex size-11 items-center justify-center rounded-xl bg-accent text-accent-foreground">
                  <point.icon className="size-5" />
                </div>
                <h3 className="font-medium text-foreground">{point.title}</h3>
                <p className="text-pretty text-sm text-muted-foreground">{point.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto w-full max-w-3xl px-6 pb-24">
        <Reveal>
          <div className="flex flex-col items-center gap-5 rounded-4xl border border-border bg-card px-8 py-14 text-center">
            <h2 className="font-[family-name:var(--font-display)] text-3xl font-medium tracking-tight text-foreground">
              Start at minute two, not minute zero.
            </h2>
            <p className="max-w-md text-pretty text-muted-foreground">
              Your first consultation takes a couple of minutes to set up. No
              account, no clinic sign-off — just you and your record.
            </p>
            <Button
              size="lg"
              className="h-12 px-8"
              nativeButton={false}
              render={<Link href="/onboarding" />}
            >
              Get started
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </Reveal>
      </section>

      <footer className="mx-auto w-full max-w-5xl px-6 pb-10 text-center text-xs text-muted-foreground">
        Cadence documents and supports — it never diagnoses or prescribes.
      </footer>

      <style>{`
        @keyframes orb-float {
          0%, 100% { transform: translate(-50%, 0) scale(1); }
          50% { transform: translate(-50%, 18px) scale(1.06); }
        }
      `}</style>
    </div>
  )
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2">
      <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="M22.5 9.5a9 9 0 1 0 2.7 8.2"
          stroke="var(--primary)"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="25.5" cy="8.5" r="3" fill="var(--secondary-foreground)" />
      </svg>
      <span className="font-[family-name:var(--font-display)] text-lg font-medium text-foreground">
        Cadence
      </span>
    </div>
  )
}
