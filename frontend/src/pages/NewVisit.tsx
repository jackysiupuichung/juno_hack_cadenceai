import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Visit } from '../api'
import VisitSummaryCards from '../components/VisitSummaryCards'

const CARE_SETTINGS = [
  { value: 'gp', label: 'GP' },
  { value: 'hospital', label: 'Hospital' },
  { value: 'emergency', label: 'Emergency' },
  { value: 'specialist', label: 'Specialist' },
]

type Stage = 'form' | 'recording' | 'review' | 'paste' | 'processing' | 'summary'

export default function NewVisit() {
  const { conditionId } = useParams<{ conditionId: string }>()
  const [stage, setStage] = useState<Stage>('form')
  const [careSetting, setCareSetting] = useState('gp')
  const [clinicianName, setClinicianName] = useState('')
  const [organisation, setOrganisation] = useState('')
  const [organisationAddress, setOrganisationAddress] = useState('')
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
    if (!conditionId) return
    setProcessingLabel('Organising your summary…')
    const created = await api.summarise({
      condition_id: conditionId,
      transcript: text,
      date: today,
      care_setting: careSetting,
      clinician_name: clinicianName,
      organisation,
      organisation_address: organisationAddress,
    })
    setProcessingLabel('Finding what you agreed…')
    setVisit(created)
    setStage('summary')
  }

  if (stage === 'summary' && visit && conditionId) {
    return <VisitSummaryView visit={visit} conditionId={conditionId} />
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
      <Link to={`/conditions/${conditionId}`} className="text-sm text-slate-400">
        ← Back
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
          <span className="mb-1 block font-medium text-slate-700">Clinic / organisation (optional)</span>
          <input
            value={organisation}
            onChange={(e) => setOrganisation(e.target.value)}
            className="w-full rounded-lg border border-slate-200 p-2.5"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium text-slate-700">Address (optional)</span>
          <input
            value={organisationAddress}
            onChange={(e) => setOrganisationAddress(e.target.value)}
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

function VisitSummaryView({ visit, conditionId }: { visit: Visit; conditionId: string }) {
  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to={`/conditions/${conditionId}`} className="text-sm text-slate-400">
        ← Back
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold text-slate-900">Visit summary</h1>

      <VisitSummaryCards visit={visit} />

      <Link
        to={`/conditions/${conditionId}`}
        className="mt-6 block rounded-xl bg-slate-900 px-4 py-3 text-center text-sm font-semibold text-white"
      >
        Back to condition
      </Link>
    </div>
  )
}
