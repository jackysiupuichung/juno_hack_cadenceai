"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  Mic,
  Square,
  RefreshCw,
  Sparkles,
  AlertCircle,
  Loader2,
  ChevronDown,
  Plus,
} from "lucide-react"
import { useApp } from "@/lib/store"
import { ApiError, api } from "@/lib/api"
import { useRecorder } from "@/lib/use-recorder"
import { formatDuration, todayISO } from "@/lib/dates"
import type { CareSetting } from "@/lib/types"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { NewConditionDialog } from "@/components/new-condition-dialog"
import { cn } from "@/lib/utils"

const CARE_SETTINGS: CareSetting[] = ["GP", "Hospital", "Emergency", "Specialist"]
const NO_CONDITION = "none"

type Phase = "form" | "transcribing" | "summarising"

function NewConsultationInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const prefillCondition = searchParams.get("condition")
  const { data, hydrated, refresh } = useApp()
  const recorder = useRecorder()

  const [conditionId, setConditionId] = React.useState<string>(
    prefillCondition ?? NO_CONDITION,
  )
  const [careSetting, setCareSetting] = React.useState<CareSetting>("GP")
  const [organisationName, setOrganisationName] = React.useState("")
  const [organisationAddress, setOrganisationAddress] = React.useState("")
  const [doctorName, setDoctorName] = React.useState("")
  const [date, setDate] = React.useState(todayISO())
  const [agreed, setAgreed] = React.useState(false)
  const [phase, setPhase] = React.useState<Phase>("form")
  const [error, setError] = React.useState<string | null>(null)
  const [showDetails, setShowDetails] = React.useState(false)
  // Set when the patient backs out of the processing screen. The in-flight
  // transcribe/summarise chain checks it before every step so a cancelled run
  // stops quietly instead of yanking the screen away moments later.
  const cancelledRef = React.useRef(false)

  React.useEffect(() => {
    if (!hydrated) return
    if (!data.profile || !data.consent) router.replace("/home")
  }, [hydrated, data.profile, data.consent, router])

  const activeConditions = data.conditions.filter((c) => c.status === "active")

  async function handleProcess() {
    if (!recorder.blob) return
    setError(null)
    cancelledRef.current = false
    try {
      setPhase("transcribing")
      const heard = await api.transcribe(recorder.blob)
      if (cancelledRef.current) return
      // The speaker-labelled form, so the summariser knows which lines are the
      // clinician's. Falls back to the flat text only when the roles could not
      // be resolved at all — a summary is still better than nothing, and the
      // backend hedges its attributions when it cannot tell who spoke.
      const transcript = heard.dialogue?.trim() || heard.text?.trim() || ""
      if (!transcript) throw new Error("The recording was empty or unclear.")

      // One call: Claude structures the summary, the commitments are
      // extracted and persisted, and the caretaker plans the interval this
      // visit just opened. What comes back is already a record, not a draft.
      setPhase("summarising")
      const visit = await api.summarise({
        condition_id: conditionId === NO_CONDITION ? undefined : conditionId,
        transcript,
        date,
        care_setting: careSetting.toLowerCase(),
        clinician_name: doctorName.trim() || undefined,
        organisation: organisationName.trim() || undefined,
        organisation_address: organisationAddress.trim() || undefined,
      })
      if (cancelledRef.current) return

      // The visit now exists on the server but not in this browser's store,
      // and the mount-time sync will not run again. Pull it in before
      // navigating, or the consultation screen finds nothing and bounces
      // straight back to home.
      await refresh()
      if (cancelledRef.current) return

      router.replace(`/consultation/${visit.id}`)
    } catch (err) {
      if (cancelledRef.current) return
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Something went wrong.",
      )
      setPhase("form")
    }
  }

  if (phase !== "form") {
    return (
      <AppShell>
        {/* A back button here matters more than most: this is exactly the
            screen a slow or failed transcribe/summarise call leaves someone
            staring at, with nothing else on it to tap. */}
        <ScreenHeader
          title="New consultation"
          onBack={() => {
            cancelledRef.current = true
            setPhase("form")
          }}
        />
        <Content className="flex flex-1 flex-col items-center justify-center text-center">
          <div className="relative flex size-20 items-center justify-center rounded-full bg-primary/10">
            <span className="absolute inline-flex size-20 animate-ping rounded-full bg-primary/10" />
            <Loader2 className="size-9 animate-spin text-primary" />
          </div>
          <div role="status">
            <h1 className="mt-8 text-xl font-semibold">
              {phase === "transcribing"
                ? "Transcribing your consultation…"
                : "Organising your summary…"}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground text-pretty">
              This can take a moment. Please keep this screen open.
            </p>
          </div>
        </Content>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <ScreenHeader title="New consultation" backHref="/home" />

      <Content className="flex flex-col gap-6 pb-10">
        <section className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="link-condition">
              Link to a condition{" "}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Select
              value={conditionId}
              onValueChange={(v) => setConditionId(v ?? NO_CONDITION)}
            >
              <SelectTrigger id="link-condition" className="h-11 w-full">
                <SelectValue>
                  {(value: string | null) =>
                    !value || value === NO_CONDITION
                      ? "Not linked yet"
                      : (activeConditions.find((c) => c.id === value)?.name ??
                        "Not linked yet")
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_CONDITION}>Not linked yet</SelectItem>
                {activeConditions.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground text-pretty">
              Not sure what this is about? Leave it unlinked — you can attach it
              to a condition later.
            </p>
            {/* Record-first must not dead-end: a patient whose condition isn't
                in the list yet can mint it here without leaving the form. */}
            <NewConditionDialog
              onCreated={(id) => setConditionId(id)}
              trigger={
                <Button
                  variant="ghost"
                  size="sm"
                  className="self-start text-muted-foreground"
                >
                  <Plus className="size-4" />
                  New condition
                </Button>
              }
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="date">Date of appointment</Label>
            <Input
              id="date"
              type="date"
              value={date}
              max={todayISO()}
              onChange={(e) => setDate(e.target.value)}
              className="h-11"
            />
          </div>
        </section>

        <label
          htmlFor="agree"
          className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4"
        >
          <Checkbox
            id="agree"
            checked={agreed}
            disabled={recorder.state !== "idle"}
            onCheckedChange={(v) => setAgreed(v === true)}
            className="mt-0.5"
          />
          <span className="text-sm leading-relaxed">
            My clinician has agreed to this consultation being recorded.
          </span>
        </label>

        <section className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-card p-6">
          {recorder.state === "idle" && (
            <>
              <button
                type="button"
                disabled={!agreed}
                onClick={recorder.start}
                aria-label="Start recording"
                className="flex size-20 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform enabled:hover:scale-105 enabled:active:scale-95 disabled:opacity-40"
              >
                <Mic className="size-8" />
              </button>
              <p className="text-sm text-muted-foreground text-pretty text-center">
                {agreed
                  ? "Tap to start recording your consultation."
                  : "Confirm your clinician has agreed before recording."}
              </p>
            </>
          )}

          {recorder.state === "recording" && (
            <>
              <div className="flex items-center gap-2 text-2xl font-semibold tabular-nums">
                <span className="inline-block size-2.5 animate-pulse rounded-full bg-destructive" />
                {formatDuration(recorder.seconds)}
              </div>
              <button
                type="button"
                onClick={recorder.stop}
                aria-label="Stop recording"
                className="flex size-20 items-center justify-center rounded-full bg-destructive/15 text-destructive transition-transform hover:scale-105 active:scale-95"
              >
                <Square className="size-7 fill-current" />
              </button>
              <p className="text-sm text-muted-foreground">Recording… tap to stop.</p>
            </>
          )}

          {recorder.state === "recorded" && recorder.url && (
            <div className="flex w-full flex-col items-center gap-4">
              <p className="text-sm font-medium">
                Recorded {formatDuration(recorder.seconds)}
              </p>
              <audio controls src={recorder.url} className="w-full" />
              <div className="flex w-full flex-col gap-2">
                <Button size="lg" className="h-12" onClick={handleProcess}>
                  <Sparkles className="size-4" />
                  Process recording
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    recorder.reset()
                    setError(null)
                  }}
                >
                  <RefreshCw className="size-4" />
                  Record again
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* The clinic, the address and the doctor's name are for the record,
            not the loop — kept behind a fold so the path to recording stays
            short. */}
        <section>
          <button
            type="button"
            onClick={() => setShowDetails((s) => !s)}
            aria-expanded={showDetails}
            className="flex w-full items-center justify-between rounded-xl px-1 py-2 text-sm font-semibold text-muted-foreground"
          >
            <span>Add visit details (optional)</span>
            <ChevronDown
              className={cn(
                "size-4 transition-transform",
                showDetails && "rotate-180",
              )}
            />
          </button>
          {showDetails && (
            <div className="mt-2 flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <Label htmlFor="care-setting">Care setting</Label>
                <Select
                  value={careSetting}
                  onValueChange={(v) => setCareSetting(v as CareSetting)}
                >
                  <SelectTrigger id="care-setting" className="h-11 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CARE_SETTINGS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="org">
                  Clinic or organisation{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="org"
                  value={organisationName}
                  onChange={(e) => setOrganisationName(e.target.value)}
                  placeholder="e.g. St Mary's Hospital"
                  className="h-11"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="address">
                  Address <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="address"
                  value={organisationAddress}
                  onChange={(e) => setOrganisationAddress(e.target.value)}
                  placeholder="e.g. 12 High Street, London"
                  className="h-11"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="doctor">
                  Doctor&apos;s name{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="doctor"
                  value={doctorName}
                  onChange={(e) => setDoctorName(e.target.value)}
                  placeholder="e.g. Dr Patel"
                  className="h-11"
                />
              </div>
            </div>
          )}
        </section>

        {recorder.error && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-xl bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {recorder.error}
          </p>
        )}
        {error && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-xl bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
          >
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {error}
          </p>
        )}
      </Content>
    </AppShell>
  )
}

export default function NewConsultationPage() {
  return (
    <React.Suspense
      fallback={
        <AppShell>
          <div role="status" className="flex flex-1 items-center justify-center">
            <span className="sr-only">Loading</span>
            <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
          </div>
        </AppShell>
      }
    >
      <NewConsultationInner />
    </React.Suspense>
  )
}
