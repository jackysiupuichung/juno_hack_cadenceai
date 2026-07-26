"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { ChevronLeft } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export function AppShell({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className="min-h-dvh w-full bg-background">
      <div
        className={cn(
          "mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background",
          className,
        )}
      >
        {children}
      </div>
    </div>
  )
}

export function ScreenHeader({
  title,
  subtitle,
  backHref,
  onBack,
  right,
  sticky = true,
  display = false,
}: {
  title: string
  subtitle?: string
  backHref?: string
  onBack?: () => void
  right?: React.ReactNode
  sticky?: boolean
  /** Render the title in the display serif — for the app's hero moments. */
  display?: boolean
}) {
  const router = useRouter()
  const showBack = Boolean(backHref || onBack)

  return (
    <header
      className={cn(
        "z-20 flex items-center gap-2 border-b border-border bg-background/85 px-4 py-3 backdrop-blur-md",
        sticky && "sticky top-0",
      )}
    >
      {showBack && (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Go back"
          className="-ml-1.5 shrink-0"
          onClick={() => {
            if (onBack) onBack()
            else if (backHref) router.push(backHref)
          }}
        >
          <ChevronLeft className="size-5" />
        </Button>
      )}
      {/* The spacer div stays even without a title so the back button and the
          right slot keep their edges. Onboarding/consent pass title="" and
          bring their own h1 — an empty heading here would still be announced. */}
      <div className="min-w-0 flex-1">
        {title !== "" && (
          <h1
            className={cn(
              "truncate text-foreground",
              display
                ? "font-[family-name:var(--font-display)] text-xl font-medium"
                : "text-base font-semibold",
            )}
          >
            {title}
          </h1>
        )}
        {subtitle && (
          <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {right}
    </header>
  )
}

export function Content({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <main className={cn("flex-1 px-4 py-5", className)}>{children}</main>
  )
}
