import { useCallback, useEffect, useRef, useState } from 'react'
import { ConversationProvider, useConversation } from '@elevenlabs/react'
import {
  api,
  VoiceUnavailableError,
  type CheckInResult,
  type CheckInSession,
  type RedFlag,
} from '../api'

interface Turn {
  role: 'user' | 'agent'
  text: string
}

interface Props {
  conditionId: string
  /** Rendered on every failure path so the patient always has a way through. */
  onUseForm: () => void
  onComplete: (result: CheckInResult) => void
}

/** Emergency first, then the rest in declared order. */
function sortFlags(flags: RedFlag[]): RedFlag[] {
  return [...flags].sort((a, b) => {
    const rank = (f: RedFlag) => (f.urgency.toLowerCase() === 'emergency' ? 0 : 1)
    return rank(a) - rank(b)
  })
}

/**
 * Red flag copy is lifted verbatim from a cited clinical source. It is rendered
 * exactly as received — never reworded, truncated or summarised.
 */
export function RedFlags({ flags }: { flags: RedFlag[] }) {
  if (flags.length === 0) return null
  return (
    <div className="space-y-3">
      {sortFlags(flags).map((flag) => {
        const emergency = flag.urgency.toLowerCase() === 'emergency'
        return (
          <div
            key={flag.flag_id}
            className={
              emergency
                ? 'rounded-2xl border-2 border-rose-600 bg-rose-50 p-4'
                : 'rounded-2xl border border-amber-300 bg-amber-50 p-4'
            }
          >
            <p
              className={`mb-2 text-xs font-semibold uppercase tracking-wide ${
                emergency ? 'text-rose-700' : 'text-amber-700'
              }`}
            >
              {flag.urgency}
            </p>
            <p
              className={`text-sm leading-relaxed ${
                emergency ? 'font-semibold text-rose-900' : 'text-amber-900'
              }`}
            >
              {flag.patient_facing}
            </p>
            <p
              className={`mt-2 text-sm leading-relaxed ${
                emergency ? 'font-semibold text-rose-900' : 'text-amber-900'
              }`}
            >
              {flag.action}
            </p>
          </div>
        )
      })}
    </div>
  )
}

type Phase = 'idle' | 'starting' | 'live' | 'saving' | 'done' | 'failed'

function VoiceCheckInInner({ conditionId, onUseForm, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [redFlags, setRedFlags] = useState<RedFlag[] | null>(null)

  // Read inside async callbacks that must not close over stale state.
  const turnsRef = useRef<Turn[]>([])
  const savedRef = useRef(false)

  const { startSession, endSession, status, isSpeaking } = useConversation({
    onMessage: ({ message, role }) => {
      const turn: Turn = { role: role === 'user' ? 'user' : 'agent', text: message }
      turnsRef.current = [...turnsRef.current, turn]
      setTurns(turnsRef.current)
    },
    onError: (message) => {
      setError(message || 'The voice connection failed.')
      setPhase('failed')
    },
  })

  const save = useCallback(async () => {
    // onDisconnect can fire alongside an explicit stop; only ever save once.
    if (savedRef.current) return
    savedRef.current = true

    const collected = turnsRef.current
    if (collected.length === 0) {
      setError('No conversation was recorded, so nothing has been saved.')
      setPhase('failed')
      return
    }

    setPhase('saving')
    const transcript = collected
      .map((t) => `${t.role === 'user' ? 'Patient' : 'Cadence'}: ${t.text}`)
      .join('\n')

    try {
      const result = await api.checkin({
        condition_id: conditionId,
        transcript,
        symptom_mentions: [],
        outcomes: [],
        covered_item_ids: [],
      })
      setRedFlags(result.red_flags ?? [])
      setPhase('done')
      onComplete(result)
    } catch (e) {
      setError(`The check-in could not be saved: ${e}`)
      setPhase('failed')
    }
  }, [conditionId, onComplete])

  // Registered here rather than in the hook options so `save` stays current.
  const saveRef = useRef(save)
  saveRef.current = save

  async function begin() {
    setError(null)
    setTurns([])
    turnsRef.current = []
    savedRef.current = false
    setRedFlags(null)
    setPhase('starting')

    // Mic permission is requested from this click, not on mount.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    } catch {
      setError(
        'Cadence could not access your microphone. Check your browser permissions, or use the form instead.',
      )
      setPhase('failed')
      return
    }

    // Token is fetched now so it cannot expire while the page sits open.
    let session: CheckInSession
    try {
      session = await api.checkinSession(conditionId)
    } catch (e) {
      if (e instanceof VoiceUnavailableError) {
        setError(`${e.message} You can use the form instead.`)
      } else {
        setError(`The voice check-in could not be started: ${e}`)
      }
      setPhase('failed')
      return
    }

    try {
      startSession({
        conversationToken: session.conversation_token,
        connectionType: 'webrtc',
        dynamicVariables: session.dynamic_variables,
      })
      setPhase('live')
    } catch (e) {
      setError(`The voice connection could not be opened: ${e}`)
      setPhase('failed')
    }
  }

  function stop() {
    endSession()
    void saveRef.current()
  }

  // Close the mic if the patient navigates away mid-call.
  useEffect(() => {
    return () => {
      endSession()
    }
  }, [endSession])

  if (phase === 'done') {
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-600">Check-in saved.</p>
        {redFlags && redFlags.length > 0 && <RedFlags flags={redFlags} />}
        {turns.length > 0 && <Transcript turns={turns} />}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">
          <p>{error}</p>
          <button onClick={onUseForm} className="mt-2 font-semibold underline">
            Use the form instead
          </button>
        </div>
      )}

      {(phase === 'idle' || phase === 'failed') && (
        <button
          onClick={begin}
          className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-sm"
        >
          {phase === 'failed' ? 'Try the voice check-in again' : 'Start voice check-in'}
        </button>
      )}

      {phase === 'starting' && <p className="text-sm text-slate-400">Connecting…</p>}

      {phase === 'live' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span
              className={`h-2 w-2 rounded-full ${
                status === 'connected' ? 'bg-emerald-600' : 'bg-slate-300'
              }`}
            />
            {status !== 'connected'
              ? 'Connecting…'
              : isSpeaking
                ? 'Cadence is speaking'
                : 'Listening'}
          </div>

          <Transcript turns={turns} />

          <button
            onClick={stop}
            className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700"
          >
            End and save check-in
          </button>
        </div>
      )}

      {phase === 'saving' && <p className="text-sm text-slate-400">Saving your check-in…</p>}
    </div>
  )
}

function Transcript({ turns }: { turns: Turn[] }) {
  if (turns.length === 0) {
    return <p className="text-xs text-slate-400">Your conversation will appear here.</p>
  }
  return (
    <div className="space-y-2">
      {turns.map((t, i) => (
        <div
          key={i}
          className={`rounded-xl p-3 text-sm ${
            t.role === 'user' ? 'ml-6 bg-emerald-600 text-white' : 'mr-6 bg-white text-slate-700'
          }`}
        >
          {t.text}
        </div>
      ))}
    </div>
  )
}

/**
 * `useConversation` must be rendered inside a `ConversationProvider`
 * (@elevenlabs/react v1.x), so the hook lives in the inner component.
 */
export default function VoiceCheckIn(props: Props) {
  return (
    <ConversationProvider>
      <VoiceCheckInInner {...props} />
    </ConversationProvider>
  )
}
