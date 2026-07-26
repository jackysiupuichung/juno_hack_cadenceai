# Cadence — Frontend Design & Flow Improvement Plan

Branch: `frontend_design_mods` · Produced from a three-lens audit (flow/IA, visual taste, accessibility/ergonomics) of `web/` on demo day. Every finding carries a file reference; fixes are scoped to hackathon hours, not days.

## Design read

Mobile-first patient companion in a `max-w-md` phone frame. The visual system is disciplined — calm teal/mint oklch palette, consistent tinting, honest empty states — but *uniformly* disciplined: every surface is `rounded-2xl border bg-card p-4`, so the next-visit brief (the product's hero artifact) drowns in its own politeness. The single coherent design move:

> **Make the brief a physical document, and let everything else recede.** One serif (Fraunces, already loaded), one shadow, one large radius, one animated moment — all spent on the sheet the patient hands the doctor. Everything else gets quieter, bigger-tapped, and honest.

---

## P0 — demo-breaking

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| 1 | **Freshly recorded consultation vanishes.** `handleProcess` never writes the summarised visit into the store (`addAppointment`/`setSummary` destructured, never called); `syncFromServer` runs once at mount, so `/consultation/[id]` misses, `synced` is already true, and the guard redirects to `/home` — where the visit also isn't. Record → two spinners → everything disappears. | `web/app/consultation/new/page.tsx:55-91`, `web/lib/store.tsx:153-159`, `web/app/consultation/[id]/page.tsx:56-61` | Expose a `refresh()` (re-run `syncFromServer`) from the store; await it before `router.replace`. |
| 2 | **The brief looks like a settings page.** Six stacked cards pixel-identical to the consultation summary screen. Nothing signals "hand this to a doctor". | `web/app/condition/[id]/brief/page.tsx:110-196` | One ruled sheet: `rounded-3xl` card with Fraunces masthead (condition, patient, interval range), `divide-y` sections, disclaimer as sheet footer. `rounded-3xl` becomes *reserved* for the brief. |
| 3 | **"Not done" wears the same friendly mint chip as "Done".** The honesty principle — the pitch — is invisible. | `web/app/condition/[id]/brief/page.tsx:128-130` | `STATUS_TONE` map: done → accent, partial/not_done → warning tints, unknown → muted. |
| 4 | **Zoom disabled app-wide** (`maximumScale: 1, userScalable: false`). Fails WCAG 1.4.4 for exactly this population. | `web/app/layout.tsx:34-35` | Delete both lines. Inputs are already 16px, so no iOS zoom regression. |

## P1 — high impact

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| 5 | **Agent-ended check-in calls never save** and show "Connecting…" over a dead call. Only a manual "End call" tap saves. | `web/app/condition/[id]/check-in/page.tsx:75-88,295-305` | Add `onDisconnect` → `save()` (savedRef already guards double-fire); show "Call ended". |
| 6 | **Record-first flow dead-ends.** Home promises "you don't need a condition first", but unlinked consultations have no check-in path and neither condition select can create a condition. | `web/app/home/page.tsx:168-172`, `web/app/consultation/new/page.tsx:126-155`, `web/app/consultation/[id]/page.tsx:277-290` | "+ New condition…" item in both selects, opening `NewConditionDialog` inline. |
| 7 | **Home's persistent CTA is the calendar; recording shrinks to a 36px icon.** The loop's entry point loses the best slot on the primary screen. | `web/app/home/page.tsx:137-147,257-274` | Swap: sticky primary = "Record a consultation"; calendar becomes a header icon with the badge count. |
| 8 | **The brief is buried and un-signposted.** Home's upcoming-appointment chips are dead divs at exactly the moment the brief matters. | `web/app/home/page.tsx:91-115` | Make each chip a link to the condition's brief ("View your brief"). |
| 9 | **No check-in entry on the condition page** — the interval hub shows overdue items with no way to answer them. | `web/app/condition/[id]/page.tsx:201-217` | Secondary "Check in" button beside the brief CTA for active conditions. |
| 10 | **Brief rebuilds (LLM call) on every open**, blocking behind a spinner. | `web/app/condition/[id]/brief/page.tsx:59-78` | Cache last brief per condition (localStorage); render instantly with a "Rebuilding…" pill; block only on first build. |
| 11 | **Primary buttons ≈ 4.03:1, error text ≈ 3.4:1** (estimated) — under AA. | `web/app/globals.css:64,72`, `web/components/ui/button.tsx` | `--primary` → `oklch(0.52 0.09 212)` (+ ring); add `--destructive-text: oklch(0.5 0.17 33)` for error copy. |
| 12 | **Button scale is sub-44px systemically** (default 32px, sm 28px, lg 36px) — pages hand-patch `h-12`. | `web/components/ui/button.tsx:22-34` | Rescale: default h-11, lg h-12, sm h-9, icon size-11; remove per-page patches. |
| 13 | **Dismiss X (~22px) sits on top of the check-in link** — a mis-tap starts a call. | `web/components/check-in-notification.tsx:88-95` | `size-11` hit area, icon stays small. |
| 14 | **No typographic hierarchy in-app; zero display moments.** 75× text-sm, 32× text-xs; largest app text is 18px; Fraunces unused where the demo lives. | `web/components/app-shell.tsx:70`, `web/app/home/page.tsx:67` | Optional `display` prop on ScreenHeader (Fraunces, text-xl); use on brief masthead + home greeting only. |
| 15 | **No async announcements anywhere** (transcribing, call status, saving, errors). | `consultation/new`, `check-in`, `brief` | `role="status"` on phase text, `role="alert"` on errors, polite live region on the call feed. |
| 16 | **Voice check-in's "speaking" state is a pulsing phone icon** — weakest live moment of the demo's beat 3. | `web/app/condition/[id]/check-in/page.tsx:283-294` | CSS 4-bar equalizer (speaking) / breathing bar (listening). No audio analysis. |
| 17 | **Back navigation fights the loop**: `router.push` grows history; consultation back is hardcoded `/home` even when linked. | `web/components/app-shell.tsx:61-64`, `web/app/consultation/[id]/page.tsx:84` | Conditional backHref to the linked condition; prefer `router.back()` when safe. |
| 18 | **Brief assembles with no motion** despite the "built from the interval" story; reveal machinery exists unused. | `web/app/condition/[id]/brief/page.tsx:89-110` | Staggered fade-up per section (existing keyframes, 80ms steps). |

## P2 — polish (do after P0/P1)

- **Landing hero recomposition** (`web/app/page.tsx:79-91`): replace blurred orb + pill badge with a miniature of the brief sheet (slight rotate, shadow-lg) beside the headline; drop "Step N" eyebrow labels. Reuses the P0-2 sheet.
- **Card language**: tappable rows get `shadow-xs` + `active:bg-muted/60`; static cards stay flat. Delete unused `components/ui/card.tsx`. (`condition-card.tsx:31`, `consultation-card.tsx:38`)
- **Tint semantics**: teal tints = time & action; mint accent = record content. Collapse primary opacities to /5, /10, /25.
- **Dark theme blocks are unbranded default-shadcn grey and currently dead** (`globals.css:95-165`): delete; fix `themeColor` mismatch in `layout.tsx:31`.
- **Metadata**: title "Consultation Companion" → "Cadence"; drop `generator: v0.app`.
- **Terminology drift**: "2 appointments" on ConditionCard → "consultations"; landing "Sign in" → "Open Cadence"; Settings "Log out" (which wipes data) → "Reset this device".
- **Calendar ergonomics**: weekday initials → Sun/Mon/…; chevrons size-11; day cells to ~44px column height; per-day `aria-label` (overdue is currently colour-only); `tabular-nums` on the grid.
- **Text floor**: `text-[10px]`/`text-[11px]` → `text-xs`; instructional copy ≥ text-sm. (interval-calendar, brief chips)
- **Form front-load**: consultation/new keeps condition + date + consent + mic on top; clinic/address/doctor collapse into "Add details (optional)". Cancel-on-back for in-flight processing (`cancelledRef`).
- **Reminders default off** so saved reminders appear nowhere (`lib/store.tsx:21`): default on.
- **Print/share the brief** ("Bring this to your appointment" has no handoff): `window.print()` + minimal print styles.
- **Heading semantics**: empty `<h1>` when `ScreenHeader title=""`; double h1s on check-in and record screens. Render h1 only when non-empty; demote body headings.
- **Home tabs**: `role=tablist` without tab keyboard semantics → plain buttons with `aria-pressed` + visible focus ring.
- **Icon/chip scale sprawl** (15 sizes): consolidate to inline 3.5/4/5 and chips 9/14/20; kill `size-4.5`, `size-11` chips.
- **Bullet-dot zoo**: four hand-rolled dot styles + a raw `●` glyph in the brief → one Dot helper.
- **Rename dialog error** not linked via `aria-describedby`/`aria-invalid`; silent loading spinners missing `sr-only` labels on 3 screens.
- Deferred (post-hackathon): "Add upcoming appointment" affordance (the next-appt card + "Brief for this appointment" label are currently unreachable through the UI); condition-page overflow menu for rename/complete/delete; brief PDF export.

## Execution

- **Wave 1** — five parallel agents with disjoint file ownership: (A) loop correctness (store/record/consultation), (B) check-in page, (C) brief-as-document, (D) tokens/buttons/shell/viewport, (E) home + calendar + condition IA + copy.
- **Wave 2** — landing hero recomposition reusing the brief sheet; cross-file polish sweep (tints, icon sizes, dots, radius, aria leftovers).
- One `next build` gate after each wave; commit per wave.

What already passes and is left alone: muted-foreground contrast (~5.3:1), reduced-motion handling, dialog focus traps, the tone-tinting logic for overdue/upcoming/warning states, and the honest empty-state copy throughout.
