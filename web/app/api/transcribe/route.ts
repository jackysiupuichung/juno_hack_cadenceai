export const maxDuration = 60

export async function POST(req: Request) {
  const apiKey = process.env.ELEVENLABS_API_KEY
  if (!apiKey) {
    return Response.json(
      {
        error:
          "Transcription isn't configured yet. Please add an ELEVENLABS_API_KEY environment variable.",
      },
      { status: 501 },
    )
  }

  try {
    const inbound = await req.formData()
    const file = inbound.get("audio")
    if (!(file instanceof Blob)) {
      return Response.json({ error: "No audio file provided." }, { status: 400 })
    }

    const outbound = new FormData()
    outbound.append("file", file, "consultation.webm")
    outbound.append("model_id", "scribe_v1")
    outbound.append("diarize", "true")

    const res = await fetch("https://api.elevenlabs.io/v1/speech-to-text", {
      method: "POST",
      headers: { "xi-api-key": apiKey },
      body: outbound,
    })

    if (!res.ok) {
      const detail = await res.text()
      console.log("[v0] ElevenLabs error:", res.status, detail)
      return Response.json(
        { error: "Transcription failed. Please try again." },
        { status: 502 },
      )
    }

    const data = (await res.json()) as {
      text?: string
      words?: Array<{ text: string; speaker_id?: string }>
    }

    // Prefer a speaker-labelled transcript when diarization data is present.
    let transcript = data.text ?? ""
    if (Array.isArray(data.words) && data.words.length > 0) {
      const lines: string[] = []
      let current = ""
      let buffer = ""
      for (const w of data.words) {
        const speaker = w.speaker_id ?? "speaker"
        if (speaker !== current) {
          if (buffer.trim()) lines.push(`${current.toUpperCase()}: ${buffer.trim()}`)
          current = speaker
          buffer = ""
        }
        buffer += w.text
      }
      if (buffer.trim()) lines.push(`${current.toUpperCase()}: ${buffer.trim()}`)
      if (lines.length > 0) transcript = lines.join("\n")
    }

    return Response.json({ transcript })
  } catch (err) {
    console.log("[v0] transcribe error:", err instanceof Error ? err.message : err)
    return Response.json(
      { error: "Transcription failed. Please try again." },
      { status: 500 },
    )
  }
}
