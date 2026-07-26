"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"

import { useApp } from "@/lib/store"
import { formatDate } from "@/lib/dates"
import { AppShell, Content, ScreenHeader } from "@/components/app-shell"
import { RecordChat } from "@/components/record-chat"

/**
 * The visit-scoped chat: ask about one consultation's record. A thin wrapper —
 * the conversation lives in RecordChat, and this page only resolves which
 * visit is behind it.
 */
export default function ConsultationAskPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const { data, synced } = useApp()

  const appointment = data.appointments.find((a) => a.id === params.id)

  // `synced`, not `hydrated` — a visit recorded elsewhere is missing from
  // this browser's cache until the server answers, and redirecting before
  // then drops the patient off a consultation that exists.
  React.useEffect(() => {
    if (synced && !appointment) router.replace("/home")
  }, [synced, appointment, router])

  if (!appointment) {
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
        subtitle={formatDate(appointment.date)}
        backHref={`/consultation/${appointment.id}`}
      />
      <Content className="flex min-h-0 flex-1 flex-col pb-4">
        <RecordChat scope="visit" visitId={appointment.id} />
      </Content>
    </AppShell>
  )
}
