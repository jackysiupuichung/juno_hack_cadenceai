import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Condition } from '../api'
import { getProfile } from '../localGate'

export default function Home() {
  const [conditions, setConditions] = useState<Condition[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showNewForm, setShowNewForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [showCompleted, setShowCompleted] = useState(false)

  const profile = getProfile()

  function refresh() {
    api.listConditions().then(setConditions).catch((e) => setError(String(e)))
  }

  useEffect(refresh, [])

  async function createCondition() {
    if (!newName.trim()) return
    await api.createCondition(newName.trim())
    setNewName('')
    setShowNewForm(false)
    refresh()
  }

  const active = conditions?.filter((c) => c.status === 'active') ?? []
  const completed = conditions?.filter((c) => c.status === 'completed') ?? []

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            {profile ? profile.name : 'Cadence'}
          </p>
          <h1 className="text-xl font-semibold text-slate-900">My Conditions</h1>
        </div>
        <Link to="/settings" className="text-sm text-slate-400">
          Settings
        </Link>
      </div>

      {error && <p className="mb-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}

      {!conditions ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <>
          {active.length === 0 && !showNewForm && (
            <p className="mb-4 text-sm text-slate-400">No conditions yet — add your first one below.</p>
          )}

          <div className="space-y-3">
            {active.map((c) => (
              <ConditionCard key={c.id} condition={c} />
            ))}
          </div>

          {showNewForm ? (
            <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <input
                autoFocus
                placeholder="e.g. Kidney Failure"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="mb-3 w-full rounded-lg border border-slate-200 p-2.5 text-sm"
              />
              <div className="flex gap-2">
                <button
                  onClick={createCondition}
                  className="flex-1 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowNewForm(false)}
                  className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-500"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowNewForm(true)}
              className="mt-4 w-full rounded-xl border-2 border-dashed border-slate-200 px-4 py-3 text-sm font-semibold text-slate-500"
            >
              + New condition
            </button>
          )}

          {completed.length > 0 && (
            <div className="mt-8">
              <button
                onClick={() => setShowCompleted((v) => !v)}
                className="mb-3 text-sm font-semibold text-slate-400"
              >
                {showCompleted ? '▾' : '▸'} Completed ({completed.length})
              </button>
              {showCompleted && (
                <div className="space-y-3">
                  {completed.map((c) => (
                    <ConditionCard key={c.id} condition={c} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ConditionCard({ condition }: { condition: Condition }) {
  return (
    <Link
      to={`/conditions/${condition.id}`}
      className={`block rounded-2xl border p-4 ${
        condition.status === 'completed'
          ? 'border-slate-100 bg-slate-50 opacity-70'
          : 'border-slate-100 bg-slate-50'
      }`}
    >
      <div className="flex items-start justify-between">
        <p className="font-medium text-slate-800">{condition.name}</p>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            condition.status === 'completed'
              ? 'bg-slate-200 text-slate-500'
              : 'bg-emerald-100 text-emerald-700'
          }`}
        >
          {condition.status === 'completed' ? 'Completed' : 'Active'}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {condition.appointment_count} appointment{condition.appointment_count === 1 ? '' : 's'}
      </p>
      {condition.reminder && (
        <p className="mt-2 rounded-lg bg-sky-50 px-2 py-1 text-xs text-sky-700">
          Upcoming: {condition.reminder.purpose || 'follow-up'} — {condition.reminder.date_or_timeframe}
        </p>
      )}
    </Link>
  )
}
