import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { API_BASE_URL, apiPost } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import { isTerminal, useInvestigation } from '../hooks/useInvestigation'
import type { InvestigationDetail, Step } from '../types/api'

const artifactUrl = (id: string) => `${API_BASE_URL}/api/v1/artifacts/${id}/download`

export function InvestigationPage() {
  const { id = '' } = useParams()
  const { data, isPending, isError, error, live } = useInvestigation(id)

  if (isPending) return <LoadingBlock label="investigation" />
  if (isError) return <ErrorBlock error={error} />

  const terminal = isTerminal(data.status)
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-slate-500">Investigation {data.id}</p>
          <h1 className="mt-1 flex items-center gap-3 text-xl font-semibold">
            <StatusBadge status={data.status} />
            {!terminal && (
              <span className="text-sm font-normal text-slate-500" aria-live="polite">
                {data.cancel_requested ? 'Cancelling…' : live ? 'Live' : 'Updating…'}
              </span>
            )}
          </h1>
        </div>
        <Actions data={data} />
      </header>

      <section
        aria-labelledby="report-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
      >
        <h2 id="report-heading" className="mb-1 text-sm font-medium text-slate-500">
          Bug report
        </h2>
        <p className="whitespace-pre-wrap text-sm">{data.bug_report}</p>
        <p className="mt-2 font-mono text-xs text-slate-500">
          start {data.start_path} · model {data.model_id} · RAG {data.rag_mode}
        </p>
      </section>

      {data.status_reason && <Outcome data={data} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Timeline steps={data.steps} />
        <EvidenceGallery data={data} />
      </div>
    </div>
  )
}

function Actions({ data }: { data: InvestigationDetail }) {
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const cancel = useMutation({
    mutationFn: () => apiPost(`/api/v1/investigations/${data.id}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['investigation', data.id] }),
  })
  const reportUrl = `${API_BASE_URL}/api/v1/investigations/${data.id}/report.md`

  async function copyReport() {
    const text = await (await fetch(reportUrl)).text()
    await navigator.clipboard.writeText(text)
    setCopied(true)
  }

  const button =
    'rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'
  return (
    <div className="flex flex-wrap gap-2">
      {!isTerminal(data.status) && (
        <button
          type="button"
          className={button}
          disabled={data.cancel_requested || cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          Cancel
        </button>
      )}
      {data.result && (
        <>
          <button type="button" className={button} onClick={copyReport}>
            {copied ? 'Copied' : 'Copy Markdown report'}
          </button>
          <a className={button} href={reportUrl} download>
            Download report
          </a>
        </>
      )}
      <Link className={button} to="/investigate">
        New investigation
      </Link>
    </div>
  )
}

function Outcome({ data }: { data: InvestigationDetail }) {
  const r = data.result
  return (
    <section
      aria-labelledby="outcome-heading"
      className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 id="outcome-heading" className="font-medium">
        Outcome
      </h2>
      <p className="text-sm">{data.status_reason}</p>
      {r && (
        <>
          {r.claimed_status && r.claimed_status !== r.status && (
            <p className="rounded bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              The agent claimed <strong>{r.claimed_status.replace('_', ' ')}</strong>, but its
              evidence did not pass verification.
            </p>
          )}
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-slate-500">Expected</dt>
            <dd>{r.expected_behaviour ?? '—'}</dd>
            <dt className="text-slate-500">Observed</dt>
            <dd>{r.observed_behaviour ?? '—'}</dd>
            <dt className="text-slate-500">Verification</dt>
            <dd className="font-mono text-xs">{r.verification.level}</dd>
          </dl>
          {r.verification.verified_evidence.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-medium">Verified observations</h3>
              <ul className="space-y-1 text-sm">
                {r.verification.verified_evidence.map((e) => (
                  <li key={`${e.step}-${e.quote}`}>
                    <span className="font-mono text-xs text-slate-500">
                      step {e.step} · {e.tool}
                    </span>{' '}
                    <q className="font-mono text-xs">{e.quote}</q>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {r.reproduction_steps.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-medium">
                Reproduction steps (reported by the agent)
              </h3>
              <ol className="list-decimal space-y-0.5 pl-5 text-sm">
                {r.reproduction_steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            </div>
          )}
          {r.hypotheses.length > 0 && (
            <div>
              <h3 className="mb-1 text-sm font-medium">Root-cause hypotheses — not verified</h3>
              <ul className="space-y-1 text-sm">
                {r.hypotheses.map((h, i) => (
                  <li key={i}>
                    <span className="font-mono text-xs text-slate-500">{h.confidence}</span>{' '}
                    {h.statement}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="font-mono text-xs text-slate-500">
            {r.run.model_calls} model calls · {r.run.browser_steps} browser actions · Chromium{' '}
            {r.run.browser_version} ·{' '}
            {r.run.estimated_cost_usd !== null
              ? `~$${r.run.estimated_cost_usd.toFixed(4)} (estimate)`
              : 'cost unknown'}
          </p>
        </>
      )}
    </section>
  )
}

function Timeline({ steps }: { steps: Step[] }) {
  return (
    <section aria-labelledby="timeline-heading">
      <h2 id="timeline-heading" className="mb-2 font-medium">
        Timeline
      </h2>
      {steps.length === 0 ? (
        <p className="text-sm text-slate-500">No steps recorded yet.</p>
      ) : (
        <ol className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white text-sm dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
          {steps.map((s) => (
            <li key={s.sequence} className="flex gap-3 px-3 py-2">
              <span className="w-8 shrink-0 font-mono text-xs text-slate-500">{s.sequence}</span>
              <span
                className={`w-28 shrink-0 font-mono text-xs ${s.ok ? '' : 'text-red-600 dark:text-red-400'}`}
              >
                {s.tool ?? s.node}
              </span>
              <span className="min-w-0 flex-1 break-words">{s.output_summary}</span>
              <span className="shrink-0 font-mono text-xs text-slate-400">{s.time_ms}ms</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function EvidenceGallery({ data }: { data: InvestigationDetail }) {
  const screenshots = data.evidence.filter((e) => e.type === 'screenshot')
  const others = data.evidence.filter((e) => e.type !== 'screenshot')
  return (
    <section aria-labelledby="evidence-heading" className="space-y-3">
      <h2 id="evidence-heading" className="font-medium">
        Evidence
      </h2>
      {data.evidence.length === 0 && (
        <p className="text-sm text-slate-500">No evidence captured yet.</p>
      )}
      {screenshots.map((e) => (
        <figure
          key={e.id}
          className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
        >
          <a href={artifactUrl(e.id)} target="_blank" rel="noreferrer">
            <img
              src={artifactUrl(e.id)}
              alt={`Screenshot: ${e.label}`}
              loading="lazy"
              className="w-full"
            />
          </a>
          <figcaption className="px-3 py-1.5 text-xs text-slate-500">
            {e.label}
            {e.step_sequence !== null && ` · step ${e.step_sequence}`}
          </figcaption>
        </figure>
      ))}
      {others.length > 0 && (
        <ul className="space-y-1 text-sm">
          {others.map((e) => (
            <li key={e.id}>
              <a
                className="text-sky-700 underline dark:text-sky-400"
                href={artifactUrl(e.id)}
                download
              >
                {e.label}
              </a>{' '}
              <span className="font-mono text-xs text-slate-500">
                {(e.size / 1024).toFixed(0)} KB · sha256 {e.sha256.slice(0, 10)}…
              </span>
            </li>
          ))}
          <li className="text-xs text-slate-500">
            Open traces with <code className="font-mono">npx playwright show-trace trace.zip</code>.
          </li>
        </ul>
      )}
    </section>
  )
}
