"use client"

import * as React from "react"

/**
 * A rain curtain hanging over the landing hero: fine vertical threads strung
 * with glass droplets. Move the pointer through it and the threads sway aside;
 * a fast swipe shakes drops loose and they fall.
 *
 * This is the p5.js "rain curtain" sketch (Verlet chains, one pinned point per
 * thread, mouse repulsion, agitation-based detachment) ported to a plain
 * canvas so the landing page does not carry the p5 runtime for a background.
 * Kept deliberately faint - the hero's reading surface is the headline and the
 * brief card, and the curtain is weather behind them, not a subject.
 *
 * Honors prefers-reduced-motion by drawing a single settled frame and never
 * starting the loop, and stops simulating while offscreen or tab-hidden.
 */

const LINE_SPACING = 44
const DROPS_PER_LINE_MIN = 4
const DROPS_PER_LINE_MAX = 8
const SUBDIVISIONS = 6
const CONSTRAINT_ITERATIONS = 12
const GRAVITY = 0.16
const AIR_DRAG = 0.995
const VELOCITY_LIMIT = 14
const REPULSION_RADIUS = 110
const DETACH_POINTER_SPEED = 26
const DETACH_PROBABILITY = 0.16
const MAX_DETACH_PER_FRAME = 2
const FALL_GRAVITY = 0.5
const FALL_DRAG = 0.99

const LINE_COLOR = "oklch(0.52 0.09 212 / 0.1)"
const DROP_CORE = "oklch(0.52 0.09 212 / 0.32)"
const DROP_EDGE = "oklch(0.72 0.06 200 / 0.14)"
const DROP_SHINE = "oklch(0.99 0.005 210 / 0.55)"

interface Point {
  x: number
  y: number
  ox: number
  oy: number
  pinned: boolean
}

interface Drop {
  pointIndex: number
  radius: number
  attached: boolean
}

interface Thread {
  points: Point[]
  restLengths: number[]
  drops: Drop[]
}

interface FallingDrop {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}

function buildThreads(width: number, height: number): Thread[] {
  const threads: Thread[] = []
  const count = Math.max(8, Math.round(width / LINE_SPACING))
  const curtainLength = Math.min(height * 0.72, 540)
  for (let i = 0; i < count; i++) {
    // Slight horizontal jitter so the curtain reads as strung, not printed.
    const x = ((i + 0.5) / count) * width + (((i * 7919) % 13) - 6)
    const dropCount =
      DROPS_PER_LINE_MIN +
      ((i * 104729) % (DROPS_PER_LINE_MAX - DROPS_PER_LINE_MIN + 1))
    const points: Point[] = [{ x, y: -6, ox: x, oy: -6, pinned: true }]
    const restLengths: number[] = []
    const drops: Drop[] = []
    const segment = curtainLength / (dropCount * SUBDIVISIONS)
    for (let d = 0; d < dropCount; d++) {
      for (let s = 0; s < SUBDIVISIONS; s++) {
        const y = points[points.length - 1].y + segment
        points.push({ x, y, ox: x, oy: y, pinned: false })
        restLengths.push(segment)
      }
      drops.push({
        pointIndex: points.length - 1,
        radius: 2.6 + ((i * 31 + d * 17) % 10) * 0.34,
        attached: true,
      })
    }
    threads.push({ points, restLengths, drops })
  }
  return threads
}

function drawScene(
  ctx: CanvasRenderingContext2D,
  threads: Thread[],
  falling: FallingDrop[],
  width: number,
  height: number,
) {
  ctx.clearRect(0, 0, width, height)

  ctx.strokeStyle = LINE_COLOR
  ctx.lineWidth = 1
  ctx.lineCap = "round"
  for (const thread of threads) {
    ctx.beginPath()
    ctx.moveTo(thread.points[0].x, thread.points[0].y)
    for (let i = 1; i < thread.points.length; i++) {
      ctx.lineTo(thread.points[i].x, thread.points[i].y)
    }
    ctx.stroke()
  }

  const drawDrop = (x: number, y: number, radius: number) => {
    const glass = ctx.createRadialGradient(x, y, 0, x, y, radius)
    glass.addColorStop(0, DROP_CORE)
    glass.addColorStop(1, DROP_EDGE)
    ctx.fillStyle = glass
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = DROP_SHINE
    ctx.beginPath()
    ctx.arc(x - radius * 0.3, y - radius * 0.35, radius * 0.28, 0, Math.PI * 2)
    ctx.fill()
  }

  for (const thread of threads) {
    for (const drop of thread.drops) {
      if (!drop.attached) continue
      const p = thread.points[drop.pointIndex]
      drawDrop(p.x, p.y, drop.radius)
    }
  }
  for (const f of falling) drawDrop(f.x, f.y, f.radius)
}

export function RainCurtain({ className }: { className?: string }) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches

    let threads: Thread[] = []
    let falling: FallingDrop[] = []
    let width = 0
    let height = 0
    let raf = 0
    let running = false
    let visible = true
    const pointer = { x: -9999, y: -9999, px: -9999, py: -9999 }

    const dpr = Math.min(window.devicePixelRatio || 1, 2)

    function resize() {
      const rect = canvas!.getBoundingClientRect()
      width = rect.width
      height = rect.height
      canvas!.width = Math.round(width * dpr)
      canvas!.height = Math.round(height * dpr)
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      threads = buildThreads(width, height)
      falling = []
      if (reduceMotion) {
        // One settled frame; the curtain simply hangs.
        drawScene(ctx!, threads, falling, width, height)
      }
    }

    function simulate() {
      const pointerSpeed = Math.hypot(
        pointer.x - pointer.px,
        pointer.y - pointer.py,
      )
      let detachedThisFrame = 0

      for (const thread of threads) {
        for (const p of thread.points) {
          if (p.pinned) continue
          let vx = (p.x - p.ox) * AIR_DRAG
          let vy = (p.y - p.oy) * AIR_DRAG + GRAVITY
          const dx = p.x - pointer.x
          const dy = p.y - pointer.y
          const dist = Math.hypot(dx, dy)
          if (dist < REPULSION_RADIUS && dist > 0.001) {
            const push = (1 - dist / REPULSION_RADIUS) * 1.1
            vx += (dx / dist) * push
            vy += (dy / dist) * push
          }
          const speed = Math.hypot(vx, vy)
          if (speed > VELOCITY_LIMIT) {
            vx = (vx / speed) * VELOCITY_LIMIT
            vy = (vy / speed) * VELOCITY_LIMIT
          }
          p.ox = p.x
          p.oy = p.y
          p.x += vx
          p.y += vy
        }

        for (let iter = 0; iter < CONSTRAINT_ITERATIONS; iter++) {
          for (let i = 0; i < thread.restLengths.length; i++) {
            const a = thread.points[i]
            const b = thread.points[i + 1]
            const dx = b.x - a.x
            const dy = b.y - a.y
            const dist = Math.hypot(dx, dy) || 0.0001
            const diff = ((thread.restLengths[i] - dist) / dist) * 0.5
            const offX = dx * diff
            const offY = dy * diff
            if (!a.pinned) {
              a.x -= offX
              a.y -= offY
            }
            if (!b.pinned) {
              b.x += offX
              b.y += offY
            }
          }
        }

        // A fast swipe through the curtain shakes drops loose.
        if (
          pointerSpeed > DETACH_POINTER_SPEED &&
          detachedThisFrame < MAX_DETACH_PER_FRAME
        ) {
          for (const drop of thread.drops) {
            if (!drop.attached || detachedThisFrame >= MAX_DETACH_PER_FRAME)
              continue
            const p = thread.points[drop.pointIndex]
            if (
              Math.hypot(p.x - pointer.x, p.y - pointer.y) <
                REPULSION_RADIUS * 1.3 &&
              Math.random() < DETACH_PROBABILITY
            ) {
              falling.push({
                x: p.x,
                y: p.y,
                vx: (p.x - p.ox) * 0.6,
                vy: Math.max(1.2, (p.y - p.oy) * 0.6),
                radius: drop.radius,
              })
              drop.attached = false
              detachedThisFrame++
            }
          }
        }
      }

      for (let i = falling.length - 1; i >= 0; i--) {
        const f = falling[i]
        f.vy += FALL_GRAVITY
        f.vx *= FALL_DRAG
        f.vy *= FALL_DRAG
        f.x += f.vx
        f.y += f.vy
        if (f.y > height + 30) falling.splice(i, 1)
      }

      pointer.px = pointer.x
      pointer.py = pointer.y
    }

    function frame() {
      if (!running) return
      simulate()
      drawScene(ctx!, threads, falling, width, height)
      raf = requestAnimationFrame(frame)
    }

    function setRunning(next: boolean) {
      if (next === running) return
      running = next
      if (running) raf = requestAnimationFrame(frame)
      else cancelAnimationFrame(raf)
    }

    function onPointerMove(e: PointerEvent) {
      const rect = canvas!.getBoundingClientRect()
      pointer.x = e.clientX - rect.left
      pointer.y = e.clientY - rect.top
    }

    function onVisibility() {
      setRunning(!reduceMotion && visible && !document.hidden)
    }

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      onVisibility()
    })
    observer.observe(canvas)

    const resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(canvas)

    resize()
    if (!reduceMotion) {
      window.addEventListener("pointermove", onPointerMove, { passive: true })
      document.addEventListener("visibilitychange", onVisibility)
      setRunning(true)
    }

    return () => {
      setRunning(false)
      observer.disconnect()
      resizeObserver.disconnect()
      window.removeEventListener("pointermove", onPointerMove)
      document.removeEventListener("visibilitychange", onVisibility)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={className}
      style={{ pointerEvents: "none" }}
    />
  )
}
