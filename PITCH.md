# LOOP — The Pitch

---

## The one-liner

> **A visit isn't an event — it's the start of an interval, and nothing spans it. LOOP captures your appointment, follows the plan through the weeks after, and walks you into the next visit with a brief that closes the loop — so every appointment starts warm instead of cold.**

## The line that lands

> **We turn every visit from a cold start into a warm one.**

---

## The five beats

### 1. The gap (25s)

> You see your doctor for eight minutes. You forget half of what's said before you reach the
> car. Over the next six weeks you're supposed to try a medication, get a blood test, watch a
> symptom — and nobody's tracking any of it. Then you go back, and the doctor, who's seen two
> hundred patients since, starts almost from scratch. The appointment starts cold. Every time.
>
> The visit isn't the problem. The *interval* is. And nothing spans the interval.

### 2. Capture (40s) — *live*

> So we capture the visit — for *you*, not the chart.
>
> *[record a short role-played consult; ElevenLabs Scribe transcribes]*
>
> Claude turns it into plain language you'll actually understand later — and it does the thing
> a normal scribe doesn't: it pulls out the *plan*. Try midodrine six weeks, then reassess. Get
> a ferritin test. Watch the dizziness. Four commitments — the things that define the next six
> weeks.

### 3. The loop (40s) — *fast-forward*

> Now the part nobody does. LOOP follows the plan through the interval.
>
> *[compress time — show the check-ins]*
>
> Week two: "booked the blood test, haven't been." Week three: "midodrine helps a bit but I get
> headaches." Week five: "nearly fainted twice — both after lunch."
>
> Thirty-second voice check-ins. No app to remember, no form to fill. Because the people who
> need this most are tired, and forget.

### 4. The brief (45s) — *the hero*

> Six weeks later, you walk back in. And instead of starting cold, you hand your doctor this.
>
> *[generate the next-visit brief]*
>
> What was agreed. What you did — the blood test still isn't done, and it says so. What happened
> — midodrine partially working, headaches, and dizziness that's now clearly *after meals*, a
> pattern the doctor never had before. The whole interval, closed, in sixty seconds.
>
> The appointment starts at minute two, not minute zero.

### 5. The vision + the line (20s)

> That's one loop. Stack them, and you have something no EHR gives a patient: a record of your
> life in the system — what was tried, what worked, what got missed — that travels with you to
> every doctor, every specialist, every city.
>
> **We turn every visit from a cold start into a warm one.**

---

## The moat — say it before they ask

> Epic ships a scribe. athenahealth gives one away free. So why hasn't this been built? Three
> walls, and they're all structural.
>
> **One — regulatory.** The moment a scribe *chases* follow-through — "did you get that test?" —
> it's suggesting action, which drifts into clinical-decision-support, a regulated medical
> device. Epic's scribe is frozen at "document, don't decide," because their health-system
> buyers won't take that liability. Patient-side, this is self-management. Same action, different
> regulatory universe.
>
> **Two — business model.** Their customer is the provider; their scribe saves provider time. A
> loop that chases follow-through *makes* provider work. They won't build against their buyer. We
> serve the patient — who they don't sell to.
>
> **Three — data ownership.** Their capture is locked in the EHR. Ours is patient-owned and
> portable by construction — which is the only way it works across a fragmented system.

---

## The honest weakness — name it, don't hide it

> The hard part isn't the product, it's distribution — there's no "my doctor turns it on" moment.
> Our wedge is the chronic-illness patient: many visits, many specialists, many "try this and
> reassess" intervals. For them the loop isn't nice-to-have, it's every appointment. That's a
> population that seeks tools out because the pain is constant — and it's exactly who Juno serves.

*(Naming the weakness makes the pitch stronger, not weaker — YC partners trust founders who see their own holes.)*

---

## Sponsor depth

| Sponsor | Line |
|---|---|
| **ElevenLabs** | "Scribe captures the visit; the voice agent runs the follow-through — thirty-second check-ins over the interval, the only channel a tired patient will actually use." |
| **Anthropic** | "Claude does the three hard reasoning jobs: plain-language summary, pulling the *plan* out of the conversation, and building the brief — honestly, including the test that didn't get done." |
| **Supabase** | "The record is patient-owned Postgres with row-level security, exposed as an MCP server — so the voice agent reads and writes the loop over the same protocol the whole thing runs on." |
| **Juno** | "Juno serves exactly our wedge — chronic illness, many visits. LOOP is the layer that makes each visit build on the last." |

---

## Answers to attacks

| They say | You say |
|---|---|
| "Epic/athena already ship scribes." | "Doctor-side, note-producing, frozen at 'document, don't decide.' We're patient-side and we close the loop — which they legally can't." |
| "Why won't they just add it?" | "Three walls: CDS regulation, a business model that opposes it, and EHR lock-in vs our portability." |
| "How do patients find it?" | "Distribution's the hard part — I won't pretend otherwise. The chronic patient seeks it out; that's the wedge, and it's Juno's population." |
| "Recording the doctor — legal?" | "Patient-records-own-visit is far simpler than clinic-recording, and it's patient-owned. Jurisdiction rules vary; we respect them." |
| "Is a summary enough?" | "A summary's a memory aid — done before. The loop is the product. The brief is made of real follow-through, including what didn't happen." |

---

## The close

> Isaac waited fourteen years, re-explaining himself every single visit. Marshall sees more
> doctors than most of us ever will.
>
> Every one of those visits started cold.
>
> **We make the next one start warm.**
