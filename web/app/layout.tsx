import { Analytics } from "@vercel/analytics/next"
import type { Metadata, Viewport } from "next"
import { Plus_Jakarta_Sans, Fraunces } from "next/font/google"
import "./globals.css"
import { AppProvider } from "@/lib/store"

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
})

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  axes: ["opsz", "SOFT"],
})

export const metadata: Metadata = {
  title: "Cadence",
  description:
    "Record, transcribe and understand your doctor appointments with clear, patient-friendly summaries.",
  // The icons exist in public/ but were never linked, so every page load
  // fell back to requesting /favicon.ico, which nothing serves — a 404 on
  // every console.
  icons: { icon: "/icon.svg", apple: "/apple-icon.png" },
}

export const viewport: Viewport = {
  colorScheme: "light",
  // sRGB of --background oklch(0.985 0.006 210), so the browser chrome
  // matches the page instead of flashing pure white.
  themeColor: "#f6fbfc",
  width: "device-width",
  initialScale: 1,
  // No zoom lock: this population pinch-zooms (WCAG 1.4.4), and inputs are
  // 16px so iOS will not auto-zoom on focus anyway.
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`light bg-background ${jakarta.variable} ${fraunces.variable}`}>
      <body className="font-sans antialiased">
        <AppProvider>{children}</AppProvider>
        {process.env.NODE_ENV === "production" && <Analytics />}
      </body>
    </html>
  )
}
