import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Visit } from '../api'
import VisitSummaryCards from '../components/VisitSummaryCards'
import VisitChat from '../components/VisitChat'

export default function VisitDetail() {
  const { conditionId, visitId } = useParams<{ conditionId: string; visitId: string }>()
  const [visit, setVisit] = useState<Visit | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!visitId) return
    api.getVisit(visitId).then(setVisit).catch((e) => setError(String(e)))
  }, [visitId])

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to={`/conditions/${conditionId}`} className="text-sm text-slate-400">
        ← Back
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold text-slate-900">Visit summary</h1>

      {error && <p className="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      {!visit ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          <VisitSummaryCards visit={visit} />
          <div className="mb-4">
            <VisitChat visitId={visit.id} />
          </div>
        </>
      )}
    </div>
  )
}
