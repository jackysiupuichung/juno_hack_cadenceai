import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type Timeline } from '../api'
import { STATUS_CLASS, STATUS_LABEL, TYPE_ICON } from '../commitmentDisplay'

const EVENT_LABEL = { visit: 'Visit', check_in: 'Check-in', brief: 'Next-visit brief' } as const
const EVENT_ACCENT = {
  visit: 'border-l-slate-300',
  check_in: 'border-l-sky-300',
  brief: 'border-l-violet-400',
} as const

export default function ConditionDetail() {
  const { conditionId } = useParams<{ conditionId: string }>()
  const navigate = useNavigate()
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [error, setError] = useState<string | null>(null)

  function refresh() {
    if (!conditionId) return
    api.timeline(conditionId).then(setTimeline).catch((e) => setError(String(e)))
  }

  useEffect(refresh, [conditionId])

  async function markCompleted() {
    if (!conditionId || !timeline) return
    await api.setConditionStatus(conditionId, timeline.condition.status === 'completed' ? 'active' : 'completed')
    refresh()
  }

  async function deleteCondition() {
    if (!conditionId) return
    if (!confirm(`Delete "${timeline?.condition.name}" and everything in it? This can't be undone.`)) return
    await api.deleteCondition(conditionId)
    navigate('/')
  }

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to="/" className="text-sm text-slate-400">
        ← My Conditions
      </Link>

      {error && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      {!timeline ? (
        <p className="mt-6 text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          <div className="mt-2 mb-6 flex items-center justify-between">
            <h1 className="text-xl font-semibold text-slate-900">{timeline.condition.name}</h1>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                timeline.condition.status === 'completed'
                  ? 'bg-slate-200 text-slate-500'
                  : 'bg-emerald-100 text-emerald-700'
              }`}
            >
              {timeline.condition.status === 'completed' ? 'Completed' : 'Active'}
            </span>
          </div>

          <section className="mb-6 rounded-2xl border border-slate-100 bg-slate-50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Open commitments</h2>
            {timeline.open_commitments.length === 0 ? (
              <p className="text-sm text-slate-400">Nothing open right now.</p>
            ) : (
              <ul className="space-y-2">
                {timeline.open_commitments.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-start gap-2 rounded-xl border border-slate-100 bg-white p-3 text-sm"
                  >
                    <span>{TYPE_ICON[c.type]}</span>
                    <span className="flex-1 text-slate-700">{c.text}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[c.status]}`}>
                      {STATUS_LABEL[c.status]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <div className="mb-6 flex gap-3">
            <Link
              to={`/conditions/${conditionId}/visit/new`}
              className="flex-1 rounded-xl bg-emerald-600 px-4 py-3 text-center text-sm font-semibold text-white shadow-sm"
            >
              + New appointment
            </Link>
            <Link
              to={`/conditions/${conditionId}/brief`}
              aria-disabled={!timeline.has_visits}
              className={`flex-1 rounded-xl px-4 py-3 text-center text-sm font-semibold shadow-sm ${
                timeline.has_visits ? 'bg-slate-900 text-white' : 'pointer-events-none bg-slate-100 text-slate-400'
              }`}
            >
              Generate brief
            </Link>
          </div>

          {timeline.open_commitments.length > 0 && (
            <div className="mb-6">
              <Link
                to={`/conditions/${conditionId}/checkin`}
                className="block rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-center text-sm font-semibold text-sky-700"
              >
                Check in now
              </Link>
            </div>
          )}

          <section className="mb-8">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Appointments</h2>
            {timeline.events.length === 0 && <p className="text-sm text-slate-400">Nothing yet.</p>}
            <ul className="space-y-2">
              {timeline.events.map((e) => (
                <li
                  key={`${e.kind}-${e.id}`}
                  className={`rounded-lg border-l-4 bg-slate-50 text-sm ${EVENT_ACCENT[e.kind]}`}
                >
                  {e.kind === 'visit' ? (
                    <Link to={`/conditions/${conditionId}/visits/${e.id}`} className="block p-3">
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>{EVENT_LABEL[e.kind]}</span>
                        <span>{e.date}</span>
                      </div>
                      <p className="mt-1 text-slate-700">{e.diagnosis_preview || e.care_setting}</p>
                    </Link>
                  ) : (
                    <div className="p-3">
                      <div className="flex justify-between text-xs text-slate-400">
                        <span>{EVENT_LABEL[e.kind]}</span>
                        <span>{e.date}</span>
                      </div>
                      <p className="mt-1 text-slate-700">
                        {e.kind === 'check_in' && (e.preview || 'Checked in')}
                        {e.kind === 'brief' && 'Next-visit brief'}
                      </p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <div className="space-y-2 border-t border-slate-100 pt-4">
            <button
              onClick={markCompleted}
              className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600"
            >
              {timeline.condition.status === 'completed' ? 'Reopen condition' : 'Mark treatment completed'}
            </button>
            <button onClick={deleteCondition} className="w-full py-2 text-xs text-rose-400">
              Delete this condition
            </button>
          </div>
        </>
      )}
    </div>
  )
}
