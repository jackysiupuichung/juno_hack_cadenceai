export function PrivacyNotice() {
  return (
    <div className="rounded-2xl bg-muted p-4 text-sm leading-relaxed text-muted-foreground">
      <p>
        Your health data stays on this device. Audio recordings are sent to
        ElevenLabs (transcription) and an AI provider (summarisation) for
        processing only, then the results are stored locally. Your recordings,
        transcripts, and summaries are saved on this device so you can view them
        later &mdash; you can delete everything at any time in Settings.
      </p>
    </div>
  )
}
