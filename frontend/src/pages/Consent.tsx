import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setConsent } from '../localGate'

export default function Consent() {
  const navigate = useNavigate()
  const [terms, setTerms] = useState(false)
  const [healthData, setHealthData] = useState(false)

  function submit() {
    setConsent({ termsAccepted: terms, healthDataProcessing: healthData })
    navigate('/')
  }

  return (
    <div className="flex min-h-svh flex-col justify-center bg-white px-6">
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Before you continue</h1>

      <p className="mb-6 rounded-xl bg-slate-50 p-4 text-sm leading-relaxed text-slate-600">
        Your health data stays private to your account. Audio recordings are sent to ElevenLabs
        (transcription) and an AI provider (summarisation) for processing only. Your recordings,
        transcripts, and summaries are stored so you can view them later — you can delete
        everything at any time in Settings.
      </p>

      <label className="mb-3 flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={terms}
          onChange={(e) => setTerms(e.target.checked)}
          className="mt-0.5"
        />
        I agree to the Terms &amp; Conditions and have read the Privacy Notice.
      </label>

      <label className="mb-6 flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={healthData}
          onChange={(e) => setHealthData(e.target.checked)}
          className="mt-0.5"
        />
        I consent to my consultations being recorded and my health data being processed as
        described in the Privacy Notice.
      </label>

      <button
        disabled={!terms || !healthData}
        onClick={submit}
        className="rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-400"
      >
        Continue
      </button>
    </div>
  )
}
