import { cn } from "@/lib/utils"
import type { ConditionStatus } from "@/lib/types"

export function StatusBadge({ status }: { status: ConditionStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        status === "active"
          ? "bg-accent text-accent-foreground"
          : "bg-muted text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "active" ? "bg-success" : "bg-muted-foreground",
        )}
      />
      {status === "active" ? "Active" : "Completed"}
    </span>
  )
}
