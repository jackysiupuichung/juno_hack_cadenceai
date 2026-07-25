import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Timeline } from '../api'
import { STATUS_CLASS, STATUS_LABEL, TYPE_ICON } from '../commitmentDisplay'

const EVENT_LABEL = { visit: 'Visit', check_in: 'Check-in', brief: 'Next-visit brief' } as const
const EVENT_ACCENT = {
  visit: 'border-l-slate-300',
  check_in: 'border-l-sky-300',
  brief: 'border-l-violet-400',
} as const

export default function Home() {
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.timeline().then(setTimeline).catch((e) => setError(String(e)))
  }, [])

  return (
    <div className="min-h-svh bg-white">
      <header className="px-5 pt-8 pb-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Cadence</p>
        <h1 className="text-xl font-semibold text-slate-900">
          {timeline?.condition.name ?? 'Your care record'}
        </h1>
      </header>

      {error && <p className="mx-5 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      <section className="mx-5 mb-6 rounded-2xl border border-slate-100 bg-slate-50 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Open commitments</h2>
        {!timeline ? (
          <p className="text-sm text-slate-400">Loading…</p>
        ) : timeline.open_commitments.length === 0 ? (
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
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[c.status]}`}
                >
                  {STATUS_LABEL[c.status]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="mx-5 mb-6 flex gap-3">
        <Link
          to="/visit/new"
          className="flex-1 rounded-xl bg-emerald-600 px-4 py-3 text-center text-sm font-semibold text-white shadow-sm"
        >
          + Record a visit
        </Link>
        <Link
          to="/brief"
          aria-disabled={!timeline?.has_visits}
          className={`flex-1 rounded-xl px-4 py-3 text-center text-sm font-semibold shadow-sm ${
            timeline?.has_visits
              ? 'bg-slate-900 text-white'
              : 'pointer-events-none bg-slate-100 text-slate-400'
          }`}
        >
          Generate brief
        </Link>
      </div>

      {timeline?.open_commitments.length ? (
        <div className="mx-5 mb-6">
          <Link
            to="/checkin"
            className="block rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-center text-sm font-semibold text-sky-700"
          >
            Check in now
          </Link>
        </div>
      ) : null}

      <section className="mx-5 pb-10">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Timeline</h2>
        {timeline?.events.length === 0 && <p className="text-sm text-slate-400">Nothing yet.</p>}
        <ul className="space-y-2">
          {timeline?.events.map((e) => (
            <li
              key={`${e.kind}-${e.id}`}
              className={`rounded-lg border-l-4 bg-slate-50 p-3 text-sm ${EVENT_ACCENT[e.kind]}`}
            >
              <div className="flex justify-between text-xs text-slate-400">
                <span>{EVENT_LABEL[e.kind]}</span>
                <span>{e.date}</span>
              </div>
              <p className="mt-1 text-slate-700">
                {e.kind === 'visit' && (e.diagnosis_preview || e.care_setting)}
                {e.kind === 'check_in' && (e.preview || 'Checked in')}
                {e.kind === 'brief' && 'Next-visit brief'}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
