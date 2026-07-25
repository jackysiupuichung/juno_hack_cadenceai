import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import {
  clearAllLocalData,
  getConsent,
  getProfile,
  getSettings,
  setProfile,
  setSettings,
  withdrawConsent,
} from '../localGate'

export default function Settings() {
  const navigate = useNavigate()
  const [profile, setProfileState] = useState(getProfile())
  const [consent] = useState(getConsent())
  const [settings, setSettingsState] = useState(getSettings())
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(profile?.name ?? '')
  const [busy, setBusy] = useState(false)

  async function saveName() {
    if (!nameDraft.trim() || !profile) return
    const updated = { ...profile, name: nameDraft.trim() }
    setProfile(updated)
    setProfileState(updated)
    setEditingName(false)
    api.setPatientName(nameDraft.trim()).catch(() => {})
  }

  function toggleReminders() {
    const updated = { remindersEnabled: !settings.remindersEnabled }
    setSettings(updated)
    setSettingsState(updated)
  }

  function doWithdrawConsent() {
    if (!confirm('Withdraw consent? You will need to re-consent before recording any more visits.')) return
    withdrawConsent()
    navigate('/consent')
  }

  async function deleteEverything() {
    if (!confirm('Delete ALL your data — every condition, appointment, and recording? This cannot be undone.')) {
      return
    }
    setBusy(true)
    try {
      await api.reset()
      clearAllLocalData()
      navigate('/onboarding')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-svh bg-white px-5 pb-10 pt-8">
      <Link to="/" className="text-sm text-slate-400">
        ← My Conditions
      </Link>
      <h1 className="mt-2 mb-6 text-xl font-semibold text-slate-900">Settings</h1>

      <section className="mb-6 rounded-2xl border border-slate-100 bg-slate-50 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Profile</h2>
        {editingName ? (
          <div className="flex gap-2">
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              className="flex-1 rounded-lg border border-slate-200 p-2 text-sm"
            />
            <button onClick={saveName} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white">
              Save
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-700">{profile?.name ?? '—'}</span>
            <button onClick={() => setEditingName(true)} className="text-slate-400 underline">
              Edit
            </button>
          </div>
        )}
        {profile?.dateOfBirth && (
          <p className="mt-1 text-xs text-slate-400">Date of birth: {profile.dateOfBirth}</p>
        )}
      </section>

      <section className="mb-6 rounded-2xl border border-slate-100 bg-slate-50 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Privacy &amp; consent</h2>
        <p className="mb-3 text-xs leading-relaxed text-slate-500">
          Your health data stays private to your account. Audio recordings are sent to ElevenLabs
          (transcription) and an AI provider (summarisation) for processing only, then the results
          are stored so you can view them later.
        </p>
        {consent ? (
          <div className="mb-3 text-xs text-slate-500">
            <p>✓ Terms &amp; Conditions accepted</p>
            <p>✓ Health data processing consented</p>
            <p className="mt-1 text-slate-400">Given {new Date(consent.timestamp).toLocaleDateString()}</p>
          </div>
        ) : (
          <p className="mb-3 text-xs text-rose-500">No consent on file.</p>
        )}
        <button onClick={doWithdrawConsent} className="text-xs font-medium text-rose-500 underline">
          Withdraw consent
        </button>
      </section>

      <section className="mb-6 rounded-2xl border border-slate-100 bg-slate-50 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-700">Follow-up reminders</h2>
            <p className="text-xs text-slate-400">Show upcoming follow-ups on the home screen.</p>
          </div>
          <button
            onClick={toggleReminders}
            className={`h-6 w-11 rounded-full transition ${
              settings.remindersEnabled ? 'bg-emerald-600' : 'bg-slate-200'
            }`}
          >
            <span
              className={`block h-5 w-5 translate-y-0.5 rounded-full bg-white shadow transition ${
                settings.remindersEnabled ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-rose-100 bg-rose-50 p-4">
        <h2 className="mb-2 text-sm font-semibold text-rose-700">Delete all my data</h2>
        <p className="mb-3 text-xs text-rose-600">
          Permanently deletes every condition, appointment, transcript, and summary. This cannot be
          undone.
        </p>
        <button
          disabled={busy}
          onClick={deleteEverything}
          className="w-full rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Deleting…' : 'Delete everything'}
        </button>
      </section>
    </div>
  )
}
