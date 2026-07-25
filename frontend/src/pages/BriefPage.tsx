import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Brief } from '../api'
import Disclaimer from '../components/Disclaimer'

export default function BriefPage() {
  const { conditionId } = useParams<{ conditionId: string }>()
  const [brief, setBrief] = useState<Brief | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!conditionId) return
    api.brief(conditionId).then(setBrief).catch((e) => setError(String(e)))
  }, [conditionId])

  if (error) {
    return (
      <div className="min-h-svh bg-white px-5 pb-10 pt-8">
        <Link to={`/conditions/${conditionId}`} className="text-sm text-slate-400">
          ← Back
        </Link>
        <p className="mt-6 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
      </div>
    )
  }

  if (!brief) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-white px-6 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-violet-600" />
        <p className="text-sm text-slate-500">Preparing your next-visit brief…</p>
      </div>
    )
  }

  const c = brief.content

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8 font-serif">
      <Link to={`/conditions/${conditionId}`} className="text-sm font-sans text-slate-400">
        ← Back
      </Link>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="mb-4 text-xs italic text-slate-400">
          Prepared by the patient from recorded consultations and self-reported check-ins.
        </p>
        <h1 className="mb-6 text-xl font-semibold text-slate-900">Next-visit brief</h1>

        <BriefSection title="What we agreed">
          {c.agreed.length === 0 ? (
            <Empty />
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              {c.agreed.map((a, i) => (
                <li key={i}>{a.text}</li>
              ))}
            </ul>
          )}
        </BriefSection>

        <BriefSection title="What I did">
          {c.did.length === 0 ? (
            <Empty />
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              {c.did.map((d, i) => (
                <li key={i}>
                  {d.text} — <span className="font-medium">{d.status.replace('_', ' ')}</span>
                </li>
              ))}
            </ul>
          )}
        </BriefSection>

        <BriefSection title="What happened">
          {c.happened.length === 0 ? (
            <Empty />
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              {c.happened.map((h, i) => (
                <li key={i}>
                  {h.text} {h.approx_timing && <span className="text-slate-400">({h.approx_timing})</span>}
                </li>
              ))}
            </ul>
          )}
        </BriefSection>

        <BriefSection title="What changed">
          {c.changed.length === 0 ? (
            <Empty />
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              {c.changed.map((ch, i) => (
                <li key={i}>
                  {ch.text} — <span className="font-medium">{ch.direction}</span>
                </li>
              ))}
            </ul>
          )}
        </BriefSection>

        {c.open_questions.length > 0 && (
          <BriefSection title="Open questions">
            <ul className="list-disc space-y-1 pl-5">
              {c.open_questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </BriefSection>
        )}

        {c.gaps.length > 0 && (
          <BriefSection title="What this record doesn't cover">
            <ul className="list-disc space-y-1 pl-5 text-slate-400">
              {c.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </BriefSection>
        )}

        <div className="font-sans">
          <Disclaimer />
        </div>
      </div>

      <button
        onClick={() => window.print()}
        className="mt-4 w-full rounded-xl bg-slate-900 px-4 py-3 font-sans text-sm font-semibold text-white"
      >
        Share / Save PDF
      </button>
    </div>
  )
}

function BriefSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-5">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      <div className="text-sm leading-relaxed text-slate-800">{children}</div>
    </div>
  )
}

function Empty() {
  return <p className="italic text-slate-400">Nothing recorded here.</p>
}
