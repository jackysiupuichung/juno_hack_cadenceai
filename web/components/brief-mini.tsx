import { CheckCircle2, FileText, TrendingUp } from "lucide-react"

/**
 * A decorative thumbnail of the next-visit brief for the landing hero.
 *
 * The hero used to show a glowing orb; the product's own artifact says more.
 * This is a static echo of brief-sheet.tsx at card scale: same masthead, same
 * primary rule, same ruled sections, and crucially the same honest status
 * contrast — one thing done, one thing not — because that candour is the
 * product shot. Purely visual, never read by assistive tech.
 */
export function BriefMini() {
  return (
    <div
      aria-hidden
      className="w-[300px] rotate-2 rounded-2xl border border-border bg-card p-4 shadow-lg sm:w-[340px]"
    >
      <p className="font-[family-name:var(--font-display)] text-base font-medium tracking-tight text-foreground">
        Next-visit brief
      </p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">
        Hypothyroidism · Week 7
      </p>

      <div className="mt-2.5 divide-y divide-border border-t-2 border-primary">
        <section className="py-2.5">
          <div className="mb-1.5 flex items-center gap-1.5">
            <FileText className="size-3 shrink-0 text-primary" />
            <p className="text-[10px] font-semibold text-foreground">
              What we agreed
            </p>
          </div>
          <ul className="flex flex-col gap-1 text-xs leading-snug text-foreground">
            <li>Start levothyroxine daily</li>
            <li>Blood test at week 6</li>
          </ul>
        </section>

        <section className="py-2.5">
          <div className="mb-1.5 flex items-center gap-1.5">
            <CheckCircle2 className="size-3 shrink-0 text-primary" />
            <p className="text-[10px] font-semibold text-foreground">
              What I did
            </p>
          </div>
          <ul className="flex flex-col gap-1.5">
            <li className="flex items-start gap-1.5 text-xs leading-snug text-foreground">
              <span className="shrink-0 rounded bg-accent px-1 py-px text-[10px] font-medium text-accent-foreground">
                Done
              </span>
              Blood test at week 6
            </li>
            <li className="flex items-start gap-1.5 text-xs leading-snug text-foreground">
              <span className="shrink-0 rounded bg-warning/25 px-1 py-px text-[10px] font-medium text-warning-foreground">
                Not done
              </span>
              Second morning dose
            </li>
          </ul>
        </section>

        <section className="py-2.5 pb-1">
          <div className="mb-1.5 flex items-center gap-1.5">
            <TrendingUp className="size-3 shrink-0 text-primary" />
            <p className="text-[10px] font-semibold text-foreground">
              What changed
            </p>
          </div>
          <p className="flex items-center gap-1.5 text-xs leading-snug text-foreground">
            <span className="size-1.5 shrink-0 rounded-full bg-primary" />
            Energy improving since week 4
          </p>
        </section>
      </div>
    </div>
  )
}
