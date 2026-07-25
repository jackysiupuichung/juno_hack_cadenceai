import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type CheckInResult, type Commitment, type RedFlag } from '../api'
import VoiceCheckIn, { RedFlags } from '../components/VoiceCheckIn'

type OutcomeStatus = 'done' | 'not_done' | 'partial' | 'changed' | 'unknown'

const STATUS_OPTIONS: { value: OutcomeStatus; label: string }[] = [
  { value: 'done', label: 'Done' },
  { value: 'not_done', label: 'Not done' },
  { value: 'partial', label: 'Partial' },
  { value: 'changed', label: 'Changed' },
]

export default function CheckIn() {
  const { conditionId } = useParams<{ conditionId: string }>()
  const [commitments, setCommitments] = useState<Commitment[] | null>(null)
  const [answers, setAnswers] = useState<Record<string, { status: OutcomeStatus; note: string }>>({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'voice' | 'form'>('voice')
  const [redFlags, setRedFlags] = useState<RedFlag[]>([])

  useEffect(() => {
    if (!conditionId) return
    api
      .timeline(conditionId)
      .then((t) => setCommitments(t.open_commitments))
      .catch((e) => setError(String(e)))
  }, [conditionId])

  function setStatus(id: string, status: OutcomeStatus) {
    setAnswers((prev) => ({ ...prev, [id]: { status, note: prev[id]?.note ?? '' } }))
  }

  function setNote(id: string, note: string) {
    setAnswers((prev) => ({ ...prev, [id]: { status: prev[id]?.status ?? 'unknown', note } }))
  }

  function handleVoiceComplete(result: CheckInResult) {
    setRedFlags(result.red_flags ?? [])
    setDone(true)
  }

  async function submit() {
    if (!conditionId) return
    setSubmitting(true)
    setError(null)
    try {
      const outcomes = Object.entries(answers).map(([commitment_id, a]) => ({
        commitment_id,
        status: a.status,
        note: a.note,
      }))
      const result = await api.checkin({ condition_id: conditionId, outcomes })
      setRedFlags(result.red_flags ?? [])
      setDone(true)
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-svh bg-white px-5 pb-10 pt-8">
        <p className="mb-6 text-lg font-semibold text-slate-900">Check-in saved.</p>
        {redFlags.length > 0 && (
          <div className="mb-6">
            <RedFlags flags={redFlags} />
          </div>
        )}
        <Link
          to={`/conditions/${conditionId}`}
          className="inline-block rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white"
        >
          Back to condition
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to={`/conditions/${conditionId}`} className="text-sm text-slate-400">
        ← Back
      </Link>
      <h1 className="mt-2 mb-1 text-xl font-semibold text-slate-900">Check in</h1>
      <p className="mb-6 text-sm text-slate-500">How did things go with what you agreed?</p>

      {error && <p className="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      {mode === 'voice' ? (
        <div className="space-y-5">
          {conditionId && (
            <VoiceCheckIn
              conditionId={conditionId}
              onUseForm={() => setMode('form')}
              onComplete={handleVoiceComplete}
            />
          )}
          <button
            onClick={() => setMode('form')}
            className="text-sm text-slate-500 underline"
          >
            Use the form instead
          </button>
        </div>
      ) : !commitments ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : commitments.length === 0 ? (
        <p className="text-sm text-slate-400">Nothing open to check in on.</p>
      ) : (
        <div className="space-y-5">
          {commitments.map((c) => (
            <div key={c.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <p className="mb-3 text-sm font-medium text-slate-800">{c.text}</p>
              <div className="mb-3 flex flex-wrap gap-2">
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setStatus(c.id, opt.value)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium ${
                      answers[c.id]?.status === opt.value
                        ? 'border-emerald-600 bg-emerald-600 text-white'
                        : 'border-slate-200 bg-white text-slate-600'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <input
                placeholder="Anything to add? (optional)"
                value={answers[c.id]?.note ?? ''}
                onChange={(e) => setNote(c.id, e.target.value)}
                className="w-full rounded-lg border border-slate-200 p-2 text-sm"
              />
            </div>
          ))}

          <button
            disabled={submitting || Object.keys(answers).length === 0}
            onClick={submit}
            className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-400"
          >
            {submitting ? 'Saving…' : 'Save check-in'}
          </button>

          <button onClick={() => setMode('voice')} className="text-sm text-slate-500 underline">
            Back to voice check-in
          </button>
        </div>
      )}
    </div>
  )
}
