"use client"

import Link from "next/link"
import {
  Mic,
  FileText,
  MessageCircleHeart,
  ClipboardCheck,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Reveal } from "@/components/reveal"
import { Wordmark } from "@/components/logo"
import { RainCurtain } from "@/components/rain-curtain"

const LOOP_STEPS = [
  {
    icon: Mic,
    title: "Record the visit",
    body: "Capture the conversation with your doctor, start to finish. No notes to scribble, nothing to remember on the way out.",
  },
  {
    icon: FileText,
    title: "Understand it instantly",
    body: "A clear, plain-language summary: what was said, what it means, what you agreed to do next.",
  },
  {
    icon: MessageCircleHeart,
    title: "Follow through, by voice",
    body: "Short check-in calls over the following weeks track what actually happened. No forms, just a 30-second call.",
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
    body: "Your record lives with you and travels with you: to a specialist, a new city, a different doctor entirely.",
  },
  {
    icon: Sparkles,
    title: "Plain language, always",
    body: "No jargon dumps. Cadence explains what happened and what's next in words that make sense.",
  },
]

export default function LandingPage() {
  // Deliberately no auto-redirect for a returning, already-onboarded patient:
  // this page is also where the logo sends people back from inside the app
  // (see Wordmark), and it needs to actually render, "Get started" included,
  // rather than bounce straight back to /home.
  return (
    <div className="relative min-h-dvh w-full">
      {/* Ambient colour field — the "something behind the glass" every glass
          surface on this page blurs. Fixed so it stays put while sections of
          glass scroll over it. Sits in its own z-0 layer, with all real
          content in a z-10 sibling — negative z-index on a `fixed` element is
          unreliable, since `fixed` escapes to the root stacking context and
          can end up painted behind the page's own opaque background. */}
      <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-background">
        <div
          className="absolute -top-24 left-[8%] h-[420px] w-[420px] rounded-full bg-primary/35 blur-3xl"
          style={{ animation: "blob-float-a 16s ease-in-out infinite" }}
        />
        <div
          className="absolute top-[35%] right-[4%] h-[380px] w-[380px] rounded-full bg-accent/60 blur-3xl"
          style={{ animation: "blob-float-b 20s ease-in-out infinite" }}
        />
        <div
          className="absolute bottom-[-10%] left-[20%] h-[460px] w-[460px] rounded-full bg-secondary/70 blur-3xl"
          style={{ animation: "blob-float-c 18s ease-in-out infinite" }}
        />
      </div>

      <div className="relative z-10">
      <header className="glass-nav sticky top-0 z-30 mx-auto flex w-full items-center justify-between px-6 py-4">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between">
          <Wordmark />
          <Button
            variant="ghost"
            size="sm"
            nativeButton={false}
            render={<Link href="/signin" />}
          >
            Sign in
          </Button>
        </div>
      </header>

      {/* Hero */}
      {/* isolate: the rain canvas sits on -z-10, and without a local stacking
          context it would paint behind the page's own background. */}
      <section className="relative isolate mx-auto flex w-full max-w-5xl flex-col items-center px-6 pb-20 pt-14 text-center sm:pb-28 sm:pt-20">
        {/* Weather, not subject: a faint interactive rain curtain hangs over
            the hero. Sway it with the pointer; a fast swipe sheds drops. */}
        <RainCurtain className="absolute inset-0 -z-10 size-full" />

        <div
          className="glass-subtle mb-6 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium text-muted-foreground"
          style={{ animation: "fade-up 500ms var(--ease-out) both" }}
        >
          <span className="inline-flex size-1.5 rounded-full bg-primary" />
          Built for the patient, not the chart
        </div>

        <h1
          className="max-w-3xl text-balance font-[family-name:var(--font-display)] text-4xl font-medium leading-[1.08] tracking-tight text-foreground sm:text-6xl"
          style={{ animation: "fade-up 600ms var(--ease-out) 60ms both" }}
        >
          Your doctor&apos;s appointment doesn&apos;t end when you leave the
          room.
        </h1>

        <p
          className="mt-6 max-w-xl text-pretty text-lg text-muted-foreground"
          style={{ animation: "fade-up 600ms var(--ease-out) 120ms both" }}
        >
          Cadence turns what was said into something you can actually use. It
          checks in with you afterward, so nothing gets lost before your next
          one.
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

        {/* A single hero glass panel — the thesis, rendered as the material
            the rest of the page is made of. */}
        <div
          className="glass mt-14 w-full max-w-2xl rounded-4xl p-1"
          style={{ animation: "fade-up 700ms var(--ease-out) 260ms both" }}
        >
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-[calc(2rem-2px)] sm:grid-cols-4">
            {LOOP_STEPS.map((step, i) => (
              <div
                key={step.title}
                className="flex flex-col items-center gap-2 bg-card/40 px-4 py-6 text-center"
              >
                <step.icon className="size-5 text-primary" strokeWidth={1.8} />
                <p className="text-xs font-medium text-foreground">{step.title}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="mx-auto w-full max-w-5xl px-6 py-16 sm:py-24">
        <Reveal className="mx-auto max-w-xl text-center">
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-medium tracking-tight text-foreground sm:text-4xl">
            One loop, every visit
          </h2>
          <p className="mt-3 text-pretty text-muted-foreground">
            The same four steps, every time, until the record is something you
            can actually stand on.
          </p>
        </Reveal>

        <div className="mt-14 flex flex-col gap-3 lg:flex-row lg:items-stretch">
          {LOOP_STEPS.flatMap((step, i) => {
            const card = (
              <Reveal key={step.title} delay={i * 70} className="lg:flex-1">
                <div className="glass flex h-full flex-col items-center gap-3 rounded-3xl p-6 text-center transition-transform duration-300 ease-(--ease-out) hover:-translate-y-1 lg:items-start lg:text-left">
                  <div className="glass-subtle flex size-12 shrink-0 items-center justify-center rounded-2xl text-primary">
                    <step.icon className="size-5" />
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
            )
            if (i === LOOP_STEPS.length - 1) return [card]
            return [
              card,
              <div
                key={`${step.title}-arrow`}
                aria-hidden
                className="flex items-center justify-center text-primary/35"
              >
                <ChevronDown className="size-5 lg:hidden" strokeWidth={2.5} />
                <ChevronRight className="hidden size-5 lg:block" strokeWidth={2.5} />
              </div>,
            ]
          })}
        </div>
      </section>

      {/* Trust */}
      <section className="mx-auto w-full max-w-5xl px-6 py-16 sm:py-24">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {TRUST_POINTS.map((point, i) => (
            <Reveal key={point.title} delay={i * 70}>
              <div className="glass flex h-full flex-col gap-3 rounded-3xl p-7">
                <div className="glass-subtle flex size-11 items-center justify-center rounded-xl text-accent-foreground">
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
          <div className="glass flex flex-col items-center gap-5 rounded-4xl px-8 py-14 text-center">
            <h2 className="font-[family-name:var(--font-display)] text-3xl font-medium tracking-tight text-foreground">
              Start at minute two, not minute zero.
            </h2>
            <p className="max-w-md text-pretty text-muted-foreground">
              Your first consultation takes a couple of minutes to set up. No
              account, no clinic sign-off. Just you and your record.
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
        Cadence documents and supports. It never diagnoses or prescribes.
      </footer>
      </div>
    </div>
  )
}
