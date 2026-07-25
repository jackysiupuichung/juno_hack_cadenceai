import { useState } from 'react'
import { api } from '../api'

interface Message {
  role: 'user' | 'assistant'
  text: string
  grounded?: boolean
}

export default function VisitChat({ visitId }: { visitId: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)

  async function submit() {
    const q = question.trim()
    if (!q || asking) return
    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setQuestion('')
    setAsking(true)
    try {
      const { answer, grounded } = await api.ask(visitId, q)
      setMessages((prev) => [...prev, { role: 'assistant', text: answer, grounded }])
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', text: `Sorry, something went wrong: ${e}` }])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Ask about this visit</h2>

      {messages.length === 0 && (
        <p className="mb-3 text-xs text-slate-400">
          e.g. "What medication was I prescribed?" or "What did the doctor say about my thyroid?"
        </p>
      )}

      <div className="mb-3 space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-xl p-3 text-sm ${
              m.role === 'user' ? 'ml-6 bg-emerald-600 text-white' : 'mr-6 bg-white text-slate-700'
            }`}
          >
            {m.text}
            {m.role === 'assistant' && m.grounded === false && (
              <p className="mt-1 text-xs italic text-amber-600">Not covered in this visit's record.</p>
            )}
          </div>
        ))}
        {asking && <div className="mr-6 rounded-xl bg-white p-3 text-sm text-slate-400">Thinking…</div>}
      </div>

      <div className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="Ask a question…"
          className="flex-1 rounded-lg border border-slate-200 p-2.5 text-sm"
        />
        <button
          disabled={!question.trim() || asking}
          onClick={submit}
          className="rounded-lg bg-emerald-600 px-4 text-sm font-semibold text-white disabled:bg-slate-200 disabled:text-slate-400"
        >
          Ask
        </button>
      </div>
    </div>
  )
}
