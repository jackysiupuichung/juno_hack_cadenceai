import Link from "next/link"
import { FileQuestion } from "lucide-react"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"

/**
 * The default framework 404 is a bare white page with no way back, which is
 * a dead end this population should never hit unsoftened. Same shell, same
 * tone as the rest of the app, one road home.
 */
export default function NotFound() {
  return (
    <AppShell>
      <div className="flex flex-1 flex-col items-center justify-center gap-5 px-6 text-center">
        <div className="flex size-14 items-center justify-center rounded-2xl bg-accent text-accent-foreground">
          <FileQuestion className="size-7" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-balance">
            This page doesn&apos;t exist
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">
            The link may be old, or the record it pointed to has been removed.
            Nothing of yours is lost.
          </p>
        </div>
        <Button size="lg" nativeButton={false} render={<Link href="/home" />}>
          Back to home
        </Button>
      </div>
    </AppShell>
  )
}
