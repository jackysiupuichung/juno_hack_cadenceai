import type { ReactNode } from 'react'
import type { Visit } from '../api'
import Disclaimer from './Disclaimer'

export default function VisitSummaryCards({ visit }: { visit: Visit }) {
  const s = visit.summary
  return (
    <>
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
    </>
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
