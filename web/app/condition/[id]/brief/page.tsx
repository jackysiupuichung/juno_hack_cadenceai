"use client"

import * as React from "react"
import { useParams } from "next/navigation"
import { AlertCircle, Loader2, Printer } from "lucide-react"

import { ApiError, type Brief, api } from "@/lib/api"
import { conditionName, useApp } from "@/lib/store"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { BriefSheet } from "@/components/brief-sheet"
import { Button } from "@/components/ui/button"

/**
 * The next-visit brief — the artifact the patient hands their doctor.
 *
 * This is the screen the whole product exists for. What makes it worth a
 * doctor's two minutes is not that it summarises the last consultation, which
 * is a memory aid anyone can build, but that it is assembled from the interval
 * that consultation opened: what was agreed, what actually got done, what
 * happened in between, and — the part that costs the most to be honest about —
 * what the record does not cover. It renders as one sheet (see BriefSheet)
 * rather than six app cards, because it is a document, and the print button
 * exists because "bring this to your appointment" sometimes means paper.
 *
 * Every build is a Claude call over the whole interval, so the last brief is
 * cached per condition in localStorage: a revisit renders the stored sheet
 * instantly while a rebuild runs quietly behind it, and the reveal animation
 * plays only on a genuinely fresh build — a document picked back up should not
 * unveil itself again.
 *
 * Nothing here composes clinical text. Every line was written by the backend,
 * where the observations are pre-written in Python precisely so no model gets
 * the chance to turn "the test was due at week 7" into "the dose may be wrong".
 * This file renders strings and adds no judgement of its own.
 */

export default function BriefPage() {
  const params = useParams<{ id: string }>()
  const conditionId = params.id
  const { data } = useApp()

  const [brief, setBrief] = React.useState<Brief | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [refreshing, setRefreshing] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [animate, setAnimate] = React.useState(false)

  const cacheKey = `cadence.brief.${conditionId}`

  const fetchBrief = React.useCallback(
    async (mode: "blocking" | "background") => {
      if (mode === "blocking") setLoading(true)
      else setRefreshing(true)
      setError(null)
      try {
        const row = await api.brief(conditionId)
        setBrief(row.content)
        // Write-through on every successful build, so the next open of this
        // screen has something to show before the server answers.
        try {
          window.localStorage.setItem(
            cacheKey,
            JSON.stringify({
              content: row.content,
              savedAt: new Date().toISOString(),
            }),
          )
        } catch {
          // Private browsing or a full quota. The brief still renders.
        }
      } catch (err) {
        setError(
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "Could not build the brief.",
        )
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [conditionId, cacheKey],
  )

  React.useEffect(() => {
    let cached: Brief | null = null
    try {
      const raw = window.localStorage.getItem(cacheKey)
      if (raw) cached = (JSON.parse(raw) as { content?: Brief }).content ?? null
    } catch {
      // An unreadable cache is the same as no cache.
    }
    if (cached) {
      setBrief(cached)
      setLoading(false)
      void fetchBrief("background")
    } else {
      // Only a first, genuinely fresh build gets the staggered reveal.
      setAnimate(true)
      void fetchBrief("blocking")
    }
  }, [cacheKey, fetchBrief])

  // Once a brief is on screen — cached or fresh — a rebuild never blanks it;
  // the sheet stays put and the pill says what's happening.
  const rebuild = React.useCallback(() => {
    void fetchBrief(brief ? "background" : "blocking")
  }, [brief, fetchBrief])

  const patientName = data.profile?.name?.trim().split(/\s+/)[0] ?? null

  return (
    <AppShell>
      {/* When the patient prints, the paper is the document alone: no app
          chrome, no phone-frame width. Everything this page renders itself is
          hidden with print:hidden; these rules cover the shell it does not
          own — the sticky header and the max-w-md column. */}
      <style>{`@media print {
        header { display: none !important; }
        main { padding: 0 !important; }
        .max-w-md { max-width: none !important; }
      }`}</style>

      <ScreenHeader
        title="Next-visit brief"
        subtitle="Bring this to your appointment"
        backHref={`/condition/${conditionId}`}
      />

      <Content className="flex flex-col gap-4 pb-10">
        {loading && (
          <div
            role="status"
            className="flex flex-col items-center gap-3 py-16 text-center"
          >
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Building your brief from the interval…
            </p>
          </div>
        )}

        {error && !loading && (
          <div
            role="alert"
            className="flex flex-col gap-3 rounded-2xl border border-warning/40 bg-warning/10 p-4 print:hidden"
          >
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-warning-foreground" />
              <p className="text-sm text-warning-foreground">{error}</p>
            </div>
            <Button variant="outline" size="sm" onClick={rebuild}>
              Try again
            </Button>
          </div>
        )}

        {refreshing && !loading && (
          <div
            role="status"
            className="flex items-center gap-1.5 self-start rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground print:hidden"
          >
            <Loader2 className="size-3 animate-spin" />
            Rebuilding…
          </div>
        )}

        {brief && !loading && (
          <>
            <BriefSheet
              brief={brief}
              conditionName={conditionName(data, conditionId)}
              patientName={patientName}
              animate={animate}
            />

            <div className="flex flex-col items-stretch gap-1 print:hidden">
              <Button variant="outline" onClick={() => window.print()}>
                <Printer />
                Print or save as PDF
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                onClick={rebuild}
              >
                Rebuild from the latest record
              </Button>
            </div>
          </>
        )}
      </Content>
    </AppShell>
  )
}
