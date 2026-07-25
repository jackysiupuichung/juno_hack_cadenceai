import { generateText, Output } from "ai"
import { z } from "zod"

export const maxDuration = 60

const summarySchema = z.object({
  patient_symptoms_summary: z.string(),
  doctor_diagnosis: z.string(),
  doctor_advice: z.string(),
  red_flags: z.array(z.string()),
  medications: z.array(
    z.object({
      name: z.string(),
      dosage: z.string(),
      frequency: z.string(),
      duration: z.string(),
      instructions: z.string(),
    }),
  ),
  things_to_avoid: z.array(z.string()),
  lifestyle_advice: z.array(z.string()),
  return_check: z.string(),
  future_plan: z.object({
    follow_up_needed: z.boolean(),
    date_or_timeframe: z.string(),
    purpose: z.string(),
  }),
})

const SYSTEM_PROMPT = `You are a medical scribe assistant. You will receive a transcript, generated from an audio recording, of a consultation between a patient and a doctor. Identify who is speaking (DOCTOR or PATIENT), then organise ONLY what was actually said into the JSON structure below.

Rules:
- Do not add, infer, or invent any medical information.
- If something was not mentioned in the transcript, return "" or [].
- Capture medication names, dosages, durations, and timings EXACTLY as the doctor states them. If a dosage is unclear or inaudible, write "unclear — please confirm with your doctor" rather than guessing.
- Write summaries in plain, patient-friendly language.
- Return valid JSON only, matching the schema. No markdown, no commentary.`

export async function POST(req: Request) {
  try {
    const { transcript } = (await req.json()) as { transcript?: string }

    if (!transcript || !transcript.trim()) {
      return Response.json(
        { error: "No transcript provided." },
        { status: 400 },
      )
    }

    const { output } = await generateText({
      model: "openai/gpt-4.1-mini",
      system: SYSTEM_PROMPT,
      prompt: `Transcript:\n\n${transcript}`,
      output: Output.object({ schema: summarySchema }),
    })

    return Response.json({ summary: output })
  } catch (err) {
    console.log("[v0] summarize error:", err instanceof Error ? err.message : err)
    return Response.json(
      { error: "We couldn't organise the summary. Please try again." },
      { status: 500 },
    )
  }
}
