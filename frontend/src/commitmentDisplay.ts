import type { Commitment } from './api'

export const TYPE_ICON: Record<Commitment['type'], string> = {
  medication: '💊',
  test: '🧪',
  watch_for: '👁️',
  followup: '📅',
  lifestyle: '🌱',
}

export const STATUS_LABEL: Record<Commitment['status'], string> = {
  pending: 'Pending',
  done: 'Done',
  not_done: 'Not done',
  changed: 'Changed',
}

export const STATUS_CLASS: Record<Commitment['status'], string> = {
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  not_done: 'bg-rose-50 text-rose-700 border-rose-200',
  changed: 'bg-sky-50 text-sky-700 border-sky-200',
}
