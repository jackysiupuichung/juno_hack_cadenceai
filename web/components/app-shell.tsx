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
}: {
  title: string
  subtitle?: string
  backHref?: string
  onBack?: () => void
  right?: React.ReactNode
  sticky?: boolean
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
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-base font-semibold text-foreground">{title}</h1>
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
