# LOOP

**The patient-side ambient scribe that closes the loop.**

Juno × Anthropic — "Build the Future of Healthcare" — London, 25–26 July 2026.

---

## The idea in one breath

A visit isn't an event — it's the start of an interval, and nothing spans it. You forget half
of what's said; the doctor forgets you by next week; the next visit starts cold. LOOP captures
your appointment *for you*, follows the plan through the weeks after (voice check-ins), and
walks you into the next visit with a **brief that closes the loop** — agreed, did, happened,
changed. Every appointment starts warm instead of cold.

**The brief is the hero. The loop is the engine.**

---

## Why it wins — the three-wall moat

Incumbent scribes (Epic, athenahealth, Nabla, Voa) are doctor-side and frozen at "document,
don't decide." LOOP does what they structurally can't:

1. **Regulatory** — chasing follow-through drifts into CDS/device territory; we're patient-side self-management.
2. **Business model** — a follow-through loop creates provider work; incumbents won't build against their buyer.
3. **Data ownership** — ours is patient-owned and portable; theirs is locked in the EHR.

**Honest weakness:** distribution. The wedge is the multi-visit chronic patient (Juno's population).

---

## Docs (read in order)

| File | Purpose |
|---|---|
| **`CLAUDE.md`** | Context, thesis, moat, what we're NOT building. **Read first.** |
| **`SPEC.md`** | Architecture, schema, the extractor + brief prompts, ElevenLabs config, seed data. |
| **`PLAN.md`** | 36h build order — loop-first, brief-as-payoff, milestone at hour 16. |
| **`PITCH.md`** | The five beats, the moat, sponsor lines, attack answers. |
| **`SETUP.md`** | Repo init, toolchain, Claude Code commands, phase prompts. |

---

## Quickstart

See `SETUP.md` for the full sequence. Short version:

```bash
mkdir loop && cd loop && git init          # drop these files in
npm i -g supabase @elevenlabs/cli
npx create-next-app@latest . --ts --app --no-tailwind
npm i @anthropic-ai/sdk @supabase/supabase-js @elevenlabs/client livekit-client@2.16.1
supabase init && supabase link --project-ref <ref> && supabase db push
cp .env.example .env.local                 # fill keys
claude                                      # open in Claude Code
```

---

## The governing rule

Build **loop-first, brief-as-payoff**. By hour 16: paste transcript → extract commitments →
generate the brief (honestly, incl. the postprandial signal). That's submittable. Live capture
is the *last* thing built — it's the riskiest dependency, and there's a paste-transcript fallback
so it can never sink the demo. Cut from the bottom of the priority stack in `PLAN.md`, never the brief.
