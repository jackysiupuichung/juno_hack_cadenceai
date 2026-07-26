# Cadence

**The patient-side ambient scribe that closes the loop between visits.**

A consultation is not an event. It is the start of an interval: "try this for six weeks, get the blood test, come back if it gets worse." Right now nothing spans that interval. The patient forgets half of what was said within minutes, the doctor forgets the patient by next week, and the next visit starts from zero.

Cadence captures the visit for the patient, follows the plan through the weeks after with short voice check-ins, and walks the patient into the next appointment with a **next-visit brief**: what we agreed, what I did, what happened, what changed. The appointment starts at minute two, not minute zero.

Built in 36 hours for the Juno x Anthropic "Build the Future of Healthcare" hackathon (London, July 2026).

## The loop

```
VISIT 1 ── capture (ElevenLabs Scribe) ──► plain-language summary + extracted commitments
                                                    │
                                     weeks of voice check-ins (ElevenLabs Agents):
                                     did it help? did the test happen? anything new?
                                                    │
                                                    ▼
VISIT 2 ◄──── THE NEXT-VISIT BRIEF ──── agreed · done · happened · changed
```

The brief is the hero; the loop is the engine. It is not a summary of the last visit (a memory aid, done before) but an account of the interval that visit opened, assembled from real check-in data. If the patient did not do the thing, the brief says so plainly. The gap is the signal the doctor needs.

## What's inside

| Piece | Role |
| --- | --- |
| **ElevenLabs Scribe** | Transcribes the recorded consultation. |
| **ElevenLabs Agents** | Runs the voice check-in calls across the interval, briefed per patient (pace, hearing, what matters to them) by the backend. |
| **Claude (Anthropic)** | Plain-language summary, commitment extraction, interval planning, the next-visit brief, and grounded ask-your-record Q&A. Every call returns validated JSON. |
| **Supabase** | The patient-owned longitudinal record: visits, check-ins, briefs, events. Portable by construction; never written back to an EHR. |
| **Clinical knowledge base (CKS / NICE)** | Grounds the disease and medication context the interval plan draws on. |
| **Django** (`backend/`) | Where every clinical decision lives. All prompts, schemas, red-flag triage, and safety boundaries are server-side Python; the browser composes no clinical text. |
| **Next.js** (`web/`) | The patient app: record, understand, check in, and the brief rendered as the document it is. |

## Safety principles

- **Documents and supports. Never diagnoses or prescribes.** Cadence summarises what was said, tracks what was agreed, and reports what happened. "The doctor said to reassess X in six weeks; here is how X went" is in scope. "You should change your dose" is not, and the Q&A layer refuses it explicitly.
- **Patient-owned, patient-carried.** No account, no clinic sign-off. The record belongs to the patient and travels with them.
- **Honest by design.** Statuses are never softened: not done reads as not done, and the brief states what the record does not cover.

## Run it

```bash
cp .env.example .env        # ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, SUPABASE_URL, SUPABASE_KEY
docker compose up --build   # backend on :8000, web on :3000
```

Or without Docker: `uv run python backend/manage.py runserver` and `cd web && npm install && npm run dev`. The web app reads `NEXT_PUBLIC_API_BASE` (defaults to `http://localhost:8000`).

First run: open http://localhost:3000, choose Get started, and record or paste a consultation transcript. A safety valve exists for demo conditions: if live audio fails, paste the transcript and the loop still runs.

## Repository map

```
backend/   Django API: capture, summarisation, interval loop, check-ins, brief, Q&A
web/       Next.js patient app
schemas/   JSON schemas for every model output
fixtures/  Demo transcripts and seed data
supabase/  Database schema
```
