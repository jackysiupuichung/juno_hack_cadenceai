import * as React from "react"
import { cn } from "@/lib/utils"

export function SummaryCard({
  icon,
  title,
  children,
  tone = "default",
  className,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
  tone?: "default" | "warning"
  className?: string
}) {
  return (
    <section
      className={cn(
        "rounded-2xl border p-4",
        tone === "warning"
          ? "border-warning/40 bg-warning/10"
          : "border-border bg-card",
        className,
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "flex size-7 items-center justify-center rounded-lg [&_svg]:size-4",
            tone === "warning"
              ? "bg-warning/25 text-warning-foreground"
              : "bg-accent text-accent-foreground",
          )}
        >
          {icon}
        </span>
        <h2
          className={cn(
            "text-sm font-semibold",
            tone === "warning" ? "text-warning-foreground" : "text-foreground",
          )}
        >
          {title}
        </h2>
      </div>
      <div className="text-sm leading-relaxed text-foreground">{children}</div>
    </section>
  )
}
