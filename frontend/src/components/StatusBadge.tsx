const GOOD = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
const WARN = 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
const BAD = 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300'
const NEUTRAL = 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200'

const TONES: Record<string, string> = {
  ok: GOOD,
  ready: GOOD,
  passed_oracle: GOOD,
  reproduced: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
  not_reproduced: NEUTRAL,
  cancelled: NEUTRAL,
  not_attempted: NEUTRAL,
  inconclusive: WARN,
  blocked: WARN,
  not_ready: WARN,
  failed: BAD,
  unavailable: BAD,
  failed_oracle: BAD,
  execution_error: BAD,
}

export function StatusBadge({ status }: { status: string }) {
  const tone = TONES[status] ?? 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300'
  return (
    <span className={`inline-flex rounded px-2 py-0.5 font-mono text-xs uppercase ${tone}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}
