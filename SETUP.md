# LOOP — Repo Setup & Claude Code

Everything to go from these docs to a running project in Claude Code.

---

## 1. Initialise the repo

```bash
# make the project and drop the .md files + starter files in
mkdir loop && cd loop
git init

# (copy in: CLAUDE.md SPEC.md PLAN.md PITCH.md SETUP.md README.md
#           .gitignore .env.example package.json
#           supabase/migrations/0001_init.sql )

git add -A
git commit -m "LOOP: project docs + schema scaffold"
```

## 2. Toolchain

```bash
# Node (v20+) and the Supabase CLI
node -v                              # need >= 20
npm i -g supabase @elevenlabs/cli

# Next.js app scaffold (TypeScript, App Router)
npx create-next-app@latest . --ts --app --no-tailwind --eslint --use-npm
# say "yes" to overwriting nothing important; keep the .md files

# deps
npm i @anthropic-ai/sdk @supabase/supabase-js @elevenlabs/client @elevenlabs/elevenlabs-js
# pin to avoid the WebRTC stall documented in PLAN.md
npm i livekit-client@2.16.1
```

## 3. Supabase

```bash
supabase init
supabase link --project-ref <your-ref>
supabase db push                     # applies migrations/0001_init.sql
# deploy the MCP edge function once written:
supabase functions deploy mcp
```

## 4. Secrets

```bash
cp .env.example .env.local
# fill in every key. NEVER commit .env.local (it's in .gitignore).
```

## 5. Open in Claude Code

```bash
claude          # terminal — or open the folder in the desktop app's Code tab
```

**First prompt (orient it, no code yet):**
```
Read CLAUDE.md, SPEC.md, and PLAN.md. Confirm you understand:
(a) the one-sentence thesis and the core loop,
(b) that the brief is the hero and the loop is the engine,
(c) the three-wall moat and what we are NOT building,
(d) the hour-16 milestone.
Then propose the exact order of files you'll build for Phase 0 and Phase 1. Don't write code yet.
```

**Then work phase by phase** from PLAN.md. Between phases:
- `/clear` — wipes chat context, keeps CLAUDE.md
- `#<note>` — appends a decision/trap to CLAUDE.md on the fly
  (e.g. `# pgvector not needed; using ilike for search`)
- `/compact` — summarise when a session runs long

**Do NOT run `/init`** — it would overwrite the CLAUDE.md you already have, which is better.

---

## Suggested phase prompts

```
Phase 0: set up supabase/migrations/0001_init.sql per SPEC.md schema, then
src/seed/pots-visit.ts with the 8 March visit, 4 commitments, 3 interval check-ins.
Make the transcript sound like a real cardiology consult and the check-ins like a
real tired person. Confirm the postprandial-dizziness detail is in the week-5 check-in.
```
```
Phase 1a: build src/agents/extract.ts (commitment extractor) with the SPEC prompt.
Run it on the seed transcript. It must produce exactly the 4 commitments with
review_after and discriminators, and must not invent un-agreed items.
```
```
Phase 1b: build src/agents/brief.ts (THE HERO). Join commitments to check-ins,
produce Agreed/Did/Happened/Flag. It must show the ferritin test as not_done with a
flag, midodrine as partial with the headache, and surface the postprandial pattern.
This is the milestone — get it rendering before anything else.
```

---

## Files included as scaffold

- `.gitignore` — ignores node_modules, .env.local, .next, supabase/.branches
- `.env.example` — the key names, no values
- `package.json` — deps pinned (incl. livekit-client@2.16.1)
- `supabase/migrations/0001_init.sql` — the full schema from SPEC.md
