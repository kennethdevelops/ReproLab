import { ApiRequestError } from '../api/client'

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="animate-pulse text-sm text-slate-500">
      Loading {label}…
    </div>
  )
}

export function ErrorBlock({ error }: { error: unknown }) {
  let message = 'Unknown error'
  if (error instanceof ApiRequestError) message = `${error.message} (${error.code})`
  else if (error instanceof Error) message = `Could not reach the API: ${error.message}`
  return (
    <div
      role="alert"
      className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      {message}
    </div>
  )
}
