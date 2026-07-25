import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ageFromDOB, setProfile } from '../localGate'
import { api } from '../api'

export default function Onboarding() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [blocked, setBlocked] = useState(false)

  if (blocked) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-white px-6 text-center">
        <p className="text-lg font-semibold text-slate-900">You must be 18 or over to use this app.</p>
        <p className="max-w-xs text-sm text-slate-500">
          This app records medical consultations and processes sensitive health information, and is
          only available to adults. If you're under 18, please ask a parent, guardian, or your
          clinician about your appointment instead.
        </p>
      </div>
    )
  }

  async function submit() {
    if (!name.trim() || !dateOfBirth) return
    if (ageFromDOB(dateOfBirth) < 18) {
      setBlocked(true)
      return
    }
    setProfile({ name: name.trim(), dateOfBirth })
    api.setPatientName(name.trim()).catch(() => {
      /* best-effort sync; onboarding still proceeds on the local device */
    })
    navigate('/consent')
  }

  return (
    <div className="flex min-h-svh flex-col justify-center bg-white px-6">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Welcome to</p>
      <h1 className="mb-8 text-2xl font-semibold text-slate-900">Cadence</h1>

      <label className="mb-4 block text-sm">
        <span className="mb-1 block font-medium text-slate-700">Your name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-slate-200 p-2.5"
        />
      </label>

      <label className="mb-6 block text-sm">
        <span className="mb-1 block font-medium text-slate-700">Date of birth</span>
        <input
          type="date"
          value={dateOfBirth}
          onChange={(e) => setDateOfBirth(e.target.value)}
          className="w-full rounded-lg border border-slate-200 p-2.5"
        />
      </label>

      <button
        disabled={!name.trim() || !dateOfBirth}
        onClick={submit}
        className="rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:bg-slate-200 disabled:text-slate-400"
      >
        Continue
      </button>
    </div>
  )
}
