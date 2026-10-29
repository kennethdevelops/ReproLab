import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiGet, apiPost } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import type { DemoCase, Project, PublicSettings } from '../types/api'

const VIEWPORTS = {
  desktop: { width: 1365, height: 768 },
  mobile: { width: 390, height: 844 },
} as const

interface Accepted {
  investigation_id: string
  status: string
}

export function NewInvestigationPage() {
  const navigate = useNavigate()
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/api/v1/projects'),
  })
  const cases = useQuery({
    queryKey: ['demo-cases'],
    queryFn: () => apiGet<DemoCase[]>('/api/v1/demo/cases'),
  })
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet<PublicSettings>('/api/v1/settings'),
  })

  const [projectId, setProjectId] = useState('')
  const [bugReport, setBugReport] = useState('')
  const [startPath, setStartPath] = useState('/')
  const [viewport, setViewport] = useState<keyof typeof VIEWPORTS>('desktop')

  const effectiveProject = projectId || projects.data?.[0]?.id || ''
  const maxChars = settings.data?.limits.max_bug_report_chars ?? 4000

  const start = useMutation({
    mutationFn: () =>
      apiPost<Accepted>('/api/v1/investigations', {
        project_id: effectiveProject,
        bug_report: bugReport,
        start_path: startPath,
        rag_mode: 'none',
        viewport: VIEWPORTS[viewport],
      }),
    onSuccess: (data) => navigate(`/investigations/${data.investigation_id}`),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    start.mutate()
  }

  function loadCase(c: DemoCase) {
    setBugReport(c.bug_report)
    setStartPath(c.start_path)
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section aria-labelledby="new-heading">
        <h1 id="new-heading" className="mb-4 text-xl font-semibold">
          New investigation
        </h1>

        {cases.data && cases.data.length > 0 && (
          <div className="mb-5">
            <h2 className="mb-2 text-sm font-medium text-slate-600 dark:text-slate-400">
              Preloaded demo bug reports
            </h2>
            <div className="flex flex-wrap gap-2">
              {cases.data.map((c) => (
                <button
                  key={c.case_id}
                  type="button"
                  onClick={() => loadCase(c)}
                  className="rounded border border-slate-300 bg-white px-3 py-1.5 text-left text-sm hover:border-sky-500 dark:border-slate-700 dark:bg-slate-900"
                >
                  <span className="font-mono text-xs text-slate-500">{c.case_id}</span> {c.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {projects.isPending && <LoadingBlock label="projects" />}
        {projects.isError && <ErrorBlock error={projects.error} />}

        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Project</span>
            <select
              value={effectiveProject}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            >
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.test_origin}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium">Bug report</span>
            <textarea
              required
              minLength={10}
              maxLength={maxChars}
              rows={6}
              value={bugReport}
              onChange={(e) => setBugReport(e.target.value)}
              placeholder="Describe what happened and what you expected."
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
            <span className="text-xs text-slate-500">
              {bugReport.length}/{maxChars}
            </span>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Start path</span>
              <input
                required
                pattern="/.*"
                value={startPath}
                onChange={(e) => setStartPath(e.target.value)}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 font-mono dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block font-medium">Viewport</span>
              <select
                value={viewport}
                onChange={(e) => setViewport(e.target.value as keyof typeof VIEWPORTS)}
                className="w-full rounded border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="desktop">Desktop 1365×768</option>
                <option value="mobile">Mobile 390×844</option>
              </select>
            </label>
          </div>

          <p className="text-xs text-slate-500">
            Repository retrieval (RAG) is not available yet; this run is browser-only.
          </p>

          {start.isError && <ErrorBlock error={start.error} />}
          <button
            type="submit"
            disabled={start.isPending || !effectiveProject || bugReport.trim().length < 10}
            className="rounded bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50"
          >
            {start.isPending ? 'Starting…' : 'Run investigation'}
          </button>
        </form>
      </section>

      <aside className="space-y-4 text-sm">
        <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-2 font-medium">Limits for this run</h2>
          {settings.data ? (
            <dl className="grid grid-cols-[1fr_auto] gap-y-1 text-xs">
              <dt>Browser actions</dt>
              <dd className="font-mono">{settings.data.limits.max_browser_steps}</dd>
              <dt>Model calls</dt>
              <dd className="font-mono">{settings.data.limits.max_model_calls}</dd>
              <dt>Wall clock</dt>
              <dd className="font-mono">{settings.data.limits.max_investigation_seconds}s</dd>
              <dt>Cost cap (estimate)</dt>
              <dd className="font-mono">${settings.data.limits.max_run_cost_usd}</dd>
            </dl>
          ) : (
            <LoadingBlock label="limits" />
          )}
          {settings.data && !settings.data.llm_configured && (
            <p role="alert" className="mt-3 text-xs text-amber-700 dark:text-amber-400">
              No model provider key is configured; runs will end as blocked.
            </p>
          )}
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          <h2 className="mb-2 text-sm font-medium text-slate-900 dark:text-slate-100">Privacy</h2>
          The browser runs on the server and may only visit the project&apos;s authorised origin.
          Your bug report, page text and screenshots are sent to the configured model provider and
          stored with the run. Do not paste secrets.
        </div>
      </aside>
    </div>
  )
}
