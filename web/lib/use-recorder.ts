"use client"

import * as React from "react"

export type RecorderState = "idle" | "recording" | "recorded"

export function useRecorder() {
  const [state, setState] = React.useState<RecorderState>("idle")
  const [seconds, setSeconds] = React.useState(0)
  const [blob, setBlob] = React.useState<Blob | null>(null)
  const [url, setUrl] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const recorderRef = React.useRef<MediaRecorder | null>(null)
  const chunksRef = React.useRef<Blob[]>([])
  const streamRef = React.useRef<MediaStream | null>(null)
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null)

  const stopTimer = React.useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const cleanupStream = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  const start = React.useCallback(async () => {
    setError(null)
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Recording isn't supported on this device or browser.")
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : undefined
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const b = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        })
        setBlob(b)
        setUrl(URL.createObjectURL(b))
        setState("recorded")
        cleanupStream()
      }
      recorder.start()
      recorderRef.current = recorder
      setSeconds(0)
      setState("recording")
      stopTimer()
      timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000)
    } catch {
      setError(
        "We couldn't access your microphone. Please allow microphone access and try again.",
      )
      cleanupStream()
    }
  }, [cleanupStream, stopTimer])

  const stop = React.useCallback(() => {
    stopTimer()
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop()
    }
  }, [stopTimer])

  const reset = React.useCallback(() => {
    stopTimer()
    cleanupStream()
    if (url) URL.revokeObjectURL(url)
    recorderRef.current = null
    chunksRef.current = []
    setBlob(null)
    setUrl(null)
    setSeconds(0)
    setState("idle")
    setError(null)
  }, [cleanupStream, stopTimer, url])

  React.useEffect(() => {
    return () => {
      stopTimer()
      cleanupStream()
      if (url) URL.revokeObjectURL(url)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { state, seconds, blob, url, error, start, stop, reset }
}
