import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, type Visit } from '../api'
import Disclaimer from '../components/Disclaimer'

const CARE_SETTINGS = [
  { value: 'gp', label: 'GP' },
  { value: 'hospital', label: 'Hospital' },
  { value: 'emergency', label: 'Emergency' },
  { value: 'specialist', label: 'Specialist' },
]

type Stage = 'form' | 'recording' | 'review' | 'paste' | 'processing' | 'summary'

export default function NewVisit() {
  const [stage, setStage] = useState<Stage>('form')
  const [careSetting, setCareSetting] = useState('gp')
  const [clinicianName, setClinicianName] = useState('')
  const [organisation, setOrganisation] = useState('')
  const [consent, setConsent] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [processingLabel, setProcessingLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [visit, setVisit] = useState<Visit | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const today = new Date().toISOString().slice(0, 10)

  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
    recorder.onstop = () => {
      setAudioBlob(new Blob(chunksRef.current, { type: 'audio/webm' }))
      stream.getTracks().forEach((t) => t.stop())
      setStage('review')
    }
    recorder.start()
    mediaRecorderRef.current = recorder
    setStage('recording')
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop()
  }

  async function processRecording() {
    if (!audioBlob) return
    setStage('processing')
    setError(null)
    try {
      setProcessingLabel('Transcribing your consultation…')
      const { text } = await api.transcribe(audioBlob)
      await runSummarise(text)
    } catch (e) {
      setError(String(e))
      setStage('review')
    }
  }

  async function processPasted() {
    setStage('processing')
    setError(null)
    try {
      await runSummarise(transcript)
    } catch (e) {
      setError(String(e))
      setStage('paste')
    }
  }

  async function runSummarise(text: string) {
    setProcessingLabel('Organising your summary…')
    const created = await api.summarise({
      transcript: text,
      date: today,
      care_setting: careSetting,
      clinician_name: clinicianName,
      organisation,
    })
    setProcessingLabel('Finding what you agreed…')
    setVisit(created)
    setStage('summary')
  }

  if (stage === 'summary' && visit) {
    return <VisitSummaryView visit={visit} />
  }

  if (stage === 'processing') {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-white px-6 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-600" />
        <p className="text-sm text-slate-500">{processingLabel}</p>
      </div>
    )
  }

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to="/" className="text-sm text-slate-400">
        ← Home
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold text-slate-900">Record a visit</h1>

      {error && <p className="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      <div className="space-y-4">
        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Care setting</span>
          <select
            value={careSetting}
            onChange={(e) => setCareSetting(e.target.value)}
            className="w-full rounded-lg border border-slate-200 p-2.5"
          >
            {CARE_SETTINGS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Clinician name (optional)</span>
          <input
            value={clinicianName}
            onChange={(e) => setClinicianName(e.target.value)}
            className="w-full rounded-lg border border-slate-200 p-2.5"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Organisation (optional)</span>
          <input
            value={organisation}
            onChange={(e) => setOrganisation(e.target.value)}
            className="w-full rounded-lg border border-slate-200 p-2.5"
          />
        </label>
      </div>

      {stage === 'form' && (
        <>
          <label className="mt-6 flex items-start gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5"
            />
            My clinician has agreed to this consultation being recorded.
          </label>

          <button
            disabled={!consent}
            onClick={startRecording}
            className="mt-4 w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-400"
          >
            ● Record
          </button>

          <button
            onClick={() => setStage('paste')}
            className="mt-3 w-full text-center text-sm text-slate-400 underline"
          >
            Paste transcript instead
          </button>
        </>
      )}

      {stage === 'recording' && (
        <div className="mt-6 flex flex-col items-center gap-4">
          <div className="h-3 w-3 animate-pulse rounded-full bg-rose-500" />
          <p className="text-sm text-slate-500">Recording…</p>
          <button
            onClick={stopRecording}
            className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white"
          >
            Stop
          </button>
        </div>
      )}

      {stage === 'review' && audioBlob && (
        <div className="mt-6 space-y-3">
          <audio controls src={URL.createObjectURL(audioBlob)} className="w-full" />
          <button
            onClick={processRecording}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm"
          >
            Process recording
          </button>
          <button onClick={() => setStage('form')} className="w-full text-center text-sm text-slate-400 underline">
            Record again
          </button>
        </div>
      )}

      {stage === 'paste' && (
        <div className="mt-6 space-y-3">
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={10}
            placeholder="Paste the consultation transcript here…"
            className="w-full rounded-lg border border-slate-200 p-3 text-sm"
          />
          <button
            disabled={!transcript.trim()}
            onClick={processPasted}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-400"
          >
            Process transcript
          </button>
        </div>
      )}
    </div>
  )
}

function VisitSummaryView({ visit }: { visit: Visit }) {
  const s = visit.summary
  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to="/" className="text-sm text-slate-400">
        ← Home
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold text-slate-900">Visit summary</h1>

      <SummaryCard title="Your symptoms">{s.patient_symptoms_summary || '—'}</SummaryCard>
      <SummaryCard title="Doctor's diagnosis">{s.doctor_diagnosis || '—'}</SummaryCard>
      <SummaryCard title="Doctor's advice">{s.doctor_advice || '—'}</SummaryCard>

      {s.red_flags.length > 0 && (
        <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <h2 className="mb-2 text-sm font-semibold text-amber-800">⚠️ When to go back</h2>
          <ul className="list-disc space-y-1 pl-4 text-sm text-amber-800">
            {s.red_flags.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {s.medications.length > 0 && (
        <div className="mb-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Medications</h2>
          <div className="space-y-2">
            {s.medications.map((m, i) => (
              <div key={i} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm">
                <p className="font-medium text-slate-800">{m.name}</p>
                <p className="text-slate-500">
                  {[m.dosage, m.frequency, m.duration].filter(Boolean).join(' · ')}
                </p>
                {m.instructions && <p className="mt-1 text-slate-600">{m.instructions}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {s.things_to_avoid.length > 0 && (
        <SummaryCard title="What to avoid">
          <ul className="list-disc space-y-1 pl-4">
            {s.things_to_avoid.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </SummaryCard>
      )}

      {s.lifestyle_advice.length > 0 && (
        <SummaryCard title="Lifestyle advice">
          <ul className="list-disc space-y-1 pl-4">
            {s.lifestyle_advice.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </SummaryCard>
      )}

      {visit.commitments.length > 0 && (
        <div className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <h2 className="mb-2 text-sm font-semibold text-emerald-800">What you agreed</h2>
          <ul className="space-y-1 text-sm text-emerald-800">
            {visit.commitments.map((c) => (
              <li key={c.id}>
                • {c.text} {c.timeframe && <span className="text-emerald-600">({c.timeframe})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="mb-4 rounded-xl border border-slate-100 p-3 text-sm">
        <summary className="cursor-pointer font-medium text-slate-600">View full transcript</summary>
        <p className="mt-2 whitespace-pre-wrap text-slate-500">{visit.transcript}</p>
      </details>

      <Disclaimer />

      <Link
        to="/"
        className="mt-6 block rounded-xl bg-slate-900 px-4 py-3 text-center text-sm font-semibold text-white"
      >
        Back to home
      </Link>
    </div>
  )
}

function SummaryCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4 rounded-2xl border border-slate-100 bg-slate-50 p-4">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">{title}</h2>
      <div className="text-sm text-slate-600">{children}</div>
    </div>
  )
}
