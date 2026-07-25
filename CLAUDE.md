# Cadence — Project Context for Claude Code

> **Read this first. Single source of truth.** Technical spec, build order, and setup commands are being rebuilt from concrete implementation rather than upfront planning.

---

## What this is

**Cadence** — the patient-side ambient scribe that closes the loop.

For **Juno × Anthropic "Build the Future of Healthcare"**, London, 25–26 July 2026 (36h).
First prize = guaranteed YC interview. Brief rewards **shipped products people love**, not research.

**Sponsors — use deeply:**

| Sponsor | Tool | Our use |
| --- | --- | --- |
| ElevenLabs | Scribe (STT) + Agents (voice) | Capture the visit; run the follow-through check-ins by voice. |
| Anthropic | Claude | Plain-language summary, commitment extraction, the next-visit brief. |
| Supabase | Postgres + pgvector + RLS | The patient-owned longitudinal record across visits. |
| Juno | (host) | YC health assistant for chronic illness. Founders: Isaac (14y to dx), Marshall (ME/CFS). |

---

## The one-sentence thesis

> **A consultation is not an event — it's the start of an interval. Right now nothing spans the interval: the doctor forgets, the patient forgets, and the next visit starts cold. Cadence captures the visit for the patient, follows the plan through the weeks after, and walks the patient into the next visit with a brief that closes the loop.**

---

## The core loop

```
VISIT 1 ──capture (ElevenLabs Scribe)──► plain-language summary + extracted commitments
                                                │
                                   weeks of follow-through (voice check-ins):
                                   did X work? did the test happen? did the symptom return?
                                                │
                                                ▼
VISIT 2 ◄──THE NEXT-VISIT BRIEF──── "here's what we agreed · here's what I did ·
   (the hero)                        here's what happened · here's what changed"
```

**The brief is the hero. The loop is the engine.** The brief is only impressive because it's *made of* real interval data — not a summary of Visit 1, but an account of the interval Visit 1 opened. **You must build the loop even though the brief is the payoff.** A summary alone is a memory aid (weak, done before). A summary + what-actually-happened-across-the-interval is novel and strong.

---

## Why this wins — the three-wall moat

Incumbent scribes (Epic ships one; athenahealth gives one free; Commure, Nabla, Voa) are **doctor-side, note-producing, and frozen at "document, don't decide."** Cadence is the thing they structurally cannot build:

1. **Regulatory wall.** The moment a scribe *chases* follow-through ("you were due for that blood test — did you get it?") it's suggesting action → drifts toward Clinical Decision Support / medical-device territory. Epic's scribe is deliberately frozen at documentation because their health-system buyers won't take device liability. **Patient-side, this is self-management, not CDS.** Same action, different regulatory universe.
2. **Business-model wall.** Incumbents sell to *providers* and optimize provider time. A loop that chases follow-through *creates* provider work. They won't build against their buyer. **Cadence serves a constituency (the patient) they don't sell to.**
3. **Data-ownership wall.** EHR capture is locked to one system; it doesn't travel to a specialist, an ER, a new city. **Cadence's artifact is patient-owned and portable by construction** — it works across fragmented care precisely because it isn't in the EHR.

Three independent walls. A YC partner will recognize all three.

---

## The honest weaknesses (name them, don't hide them)

1. **Distribution is the real problem, not the product.** No natural acquisition moment like "my doctor uses it." Consumer-health acquisition is slow. **Say this in the pitch.** The answer is the chronic-patient wedge (below), where the user seeks it out because the pain is constant.
2. **Consent/recording law.** Patient-records-own-visit is far simpler than clinic-recording, but varies by jurisdiction (one- vs two-party consent). Patient-owned framing is the mitigation.
3. **Retention.** The summary is one-time value; the *loop* is what creates recurring engagement. Retention lives in the loop.

## The wedge

**The multi-visit chronic patient** — many specialists, many "let's try this and reassess" intervals. For a one-off cold, the loop is nice-to-have. For chronic illness it's essential and used every cycle. This is the beachhead. It's also Juno's exact population, and the founders live it.

---

## The vision (the slide that gestures at depth)

As briefs accumulate, Cadence becomes a **longitudinal record** — which can later be re-read for *what was missed* (the evidence nobody asked about) and *what matters* (the patient's values). That's the alignment vision: the loop-closing record is the substrate a reasoning layer eventually sits on. **Ship the concrete loop; gesture at the profound record.** Don't build the reasoning layer in 36h — just show the record it produces and name where it goes.

---

## Non-negotiable principles

1. **Patient-owned, patient-carried.** The record belongs to the patient; the brief is something they bring. This is the moat AND the regulatory safety AND the portability. Never build toward EHR write-back.
2. **Document and support — never diagnose or prescribe.** Cadence summarizes what was said, tracks what was agreed, and reports what happened. It does not decide. This keeps us the safe side of CDS. "The doctor said to reassess X in 6 weeks; here's how X went" is safe. "You should increase your dose" is not.
3. **The loop is made of real interval data.** The brief must visibly aggregate genuine follow-through, not fabricate. If the loop didn't run, the brief is just a scribe.
4. **Voice for the follow-through.** Chronic patients tire easily and forget; a 30-second voice check-in beats a form. Fatigue is a core symptom of the wedge population.
5. **Honest about what was and wasn't said.** If the patient didn't do the thing, the brief says so plainly — that's the useful signal for the doctor, not something to paper over.

---

## What we are NOT building

- ❌ A doctor-side scribe / SOAP-note generator (Epic, Nabla, Voa own this — commoditized)
- ❌ EHR / Epic / FHIR write-back (regulatory + integration wall; also kills portability)
- ❌ Anything that suggests treatment changes (CDS line)
- ❌ A wearable foundation model (rejected in prior explorations: env risk, unreadable)
- ❌ Auth, onboarding, multi-patient management, settings pages
- ❌ The full reasoning/alignment layer (that's the vision slide, not the 36h build)

---

## Demo (build toward this)

The value spans weeks, but the demo is 3 minutes — so **compress time**:

| Beat | Content |
| --- | --- |
| 1. The gap | "A visit isn't an event, it's the start of an interval. Nothing spans it. You forget half of what's said within minutes; the doctor forgets you by next week; the next visit starts from zero." |
| 2. **Capture (live)** | Record a short simulated Visit 1 (you + a teammate role-play doctor/patient). ElevenLabs Scribe transcribes. Claude produces the plain-language summary + extracts the commitments ("try X 6 weeks, get blood test, return if dizziness"). |
| 3. **The loop (fast-forward)** | Compress the interval: show 2–3 voice check-ins over "6 weeks" — did X help, did the test happen, did the symptom return. Real data lands in the record. |
| 4. **THE BRIEF (hero)** | Generate the next-visit brief: agreed vs done vs happened vs changed. The patient walks into Visit 2 and hands the doctor *this*. The appointment starts at minute two, not minute zero. |
| 5. The vision + the line | "This is one loop. Stack them and you have a record of a life in the system — what was tried, what worked, what got missed. **We turn every visit from a cold start into a warm one.**" |

**Safety valve:** if live audio capture fails, fall back to a pre-recorded/pasted transcript for Visit 1 and keep the loop + brief. The brief is the hero; protect it.

---

## Anticipated attacks (have answers)

| Attack | Answer |
| --- | --- |
| "Epic/athena already ship scribes." | "Doctor-side, note-producing, frozen at 'document, don't decide.' We're patient-side and we close the loop — which they can't, because chasing follow-through drifts into CDS liability their buyers won't take." |
| "Why won't they just add it?" | "Three walls: regulatory (CDS line), business model (it creates provider work, against their buyer), and data ownership (ours is portable, theirs is locked to the EHR)." |
| "How do patients find it?" | "Honest answer: distribution is the hard part. Our wedge is the chronic patient who seeks it out because the pain is every visit, every specialist, every interval. That's Juno's population." |
| "Isn't recording the doctor legally fraught?" | "Patient-records-own-visit is far simpler than clinic-recording, and it's patient-owned. We surface consent handling; jurisdiction rules vary and we respect them." |
| "Is a summary enough?" | "A summary is a memory aid — done before. The loop is the product: we span the interval and close it back to the clinic. The brief is made of real follow-through." |

---

## Working conventions

- **TypeScript** for app + Edge Functions. Python only if genuinely easier.
- **Small.** 36 hours. One patient, one loop, one brief, one screen. Resist abstraction.
- **Every LLM call returns JSON.** Prompt JSON-only, parse defensively, log raw.
- **Commit often. Working > elegant.**
- **When stuck >30 min on a dependency, cut it** (see PLAN.md cut lines).
- **Do not build** toward EHR write-back, auth, or multi-patient.
