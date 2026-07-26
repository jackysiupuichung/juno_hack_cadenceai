"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"

import { useApp } from "@/lib/store"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { RecordChat } from "@/components/record-chat"

/**
 * The condition-scoped chat: ask across every visit and check-in recorded for
 * this condition. A thin wrapper — the conversation lives in RecordChat, and
 * this page only resolves which record is behind it.
 */
export default function ConditionAskPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { data, synced } = useApp()

  const condition = data.conditions.find((c) => c.id === params.id)

  // Waits for `synced`, not `hydrated` — same rule as the sibling pages: a
  // condition the server holds but this browser has never cached is absent
  // until the server answers, and redirecting in that window bounces the
  // patient off a record that is about to arrive.
  React.useEffect(() => {
    if (synced && !condition) router.replace("/home")
  }, [synced, condition, router])

  if (!condition) {
    return (
      <AppShell>
        <ScreenHeader title="Ask your record" backHref="/home" />
        <div role="status" className="flex flex-1 items-center justify-center">
          <span className="sr-only">Loading</span>
          <div className="size-6 animate-spin rounded-full border-2 border-muted border-t-primary" />
        </div>
      </AppShell>
    )
  }

  return (
    // h-dvh rather than the shell's min-h-dvh: the feed scrolls inside the
    // page so the input row never leaves the screen.
    <AppShell className="h-dvh">
      <ScreenHeader
        title="Ask your record"
        subtitle={condition.name}
        backHref={`/condition/${condition.id}`}
      />
      <Content className="flex min-h-0 flex-1 flex-col pb-4">
        <RecordChat scope="condition" conditionId={condition.id} />
      </Content>
    </AppShell>
  )
}
