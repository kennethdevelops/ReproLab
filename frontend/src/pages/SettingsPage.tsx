import { useQuery } from '@tanstack/react-query'
import { API_BASE_URL, apiGet } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import type { PublicSettings, Readiness } from '../types/api'

async function fetchReadiness(): Promise<Readiness> {
  // /readyz answers 503 with a valid body when a dependency is down; show it instead of failing.
  const response = await fetch(`${API_BASE_URL}/readyz`)
  return (await response.json()) as Readiness
}

export function SettingsPage() {
  const readiness = useQuery({ queryKey: ['readyz'], queryFn: fetchReadiness })
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet<PublicSettings>('/api/v1/settings'),
  })

  return (
    <div className="space-y-8">
      <section aria-labelledby="health-heading">
        <h1 id="health-heading" className="mb-3 text-xl font-semibold">
          System health
        </h1>
        {readiness.isPending && <LoadingBlock label="health" />}
        {readiness.isError && <ErrorBlock error={readiness.error} />}
        {readiness.data && (
          <ul className="space-y-1 text-sm">
            <li>
              API: <StatusBadge status={readiness.data.status} />
            </li>
            {Object.entries(readiness.data.checks).map(([name, state]) => (
              <li key={name}>
                {name}: <StatusBadge status={state} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="settings-heading">
        <h2 id="settings-heading" className="mb-3 text-lg font-semibold">
          Configuration
        </h2>
        {settings.isPending && <LoadingBlock label="settings" />}
        {settings.isError && <ErrorBlock error={settings.error} />}
        {settings.data && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-500">Mode</dt>
            <dd className="font-mono">{settings.data.app_mode}</dd>
            <dt className="text-slate-500">Model</dt>
            <dd className="font-mono">
              {settings.data.llm_provider} / {settings.data.llm_model}{' '}
              <StatusBadge status={settings.data.llm_configured ? 'ok' : 'unavailable'} />
            </dd>
            <dt className="text-slate-500">Embeddings</dt>
            <dd className="font-mono">
              {settings.data.embedding_provider} / {settings.data.embedding_model}
            </dd>
            <dt className="text-slate-500">Demo target</dt>
            <dd className="font-mono">{settings.data.demo_allowed_origin}</dd>
            {Object.entries(settings.data.limits).map(([name, value]) => (
              <div key={name} className="contents">
                <dt className="text-slate-500">{name}</dt>
                <dd className="font-mono">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  )
}
