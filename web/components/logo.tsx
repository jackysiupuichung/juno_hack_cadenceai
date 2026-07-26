import Link from "next/link"
import { cn } from "@/lib/utils"

export function LogoMark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M22.5 9.5a9 9 0 1 0 2.7 8.2"
        stroke="var(--primary)"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="25.5" cy="8.5" r="3" fill="var(--secondary-foreground)" />
    </svg>
  )
}

/** The one logo, everywhere — clicking it always goes home to the landing
 * page, the same way clicking a wordmark does on nearly every site. */
export function Wordmark({
  className,
  iconSize = 26,
  showText = true,
}: {
  className?: string
  iconSize?: number
  showText?: boolean
}) {
  return (
    <Link
      href="/"
      aria-label="Cadence home"
      className={cn(
        "flex items-center gap-2 transition-opacity duration-150 ease-(--ease-out) hover:opacity-75 active:opacity-60",
        className,
      )}
    >
      <LogoMark size={iconSize} />
      {showText && (
        <span className="font-[family-name:var(--font-display)] text-lg font-medium text-foreground">
          Cadence
        </span>
      )}
    </Link>
  )
}
