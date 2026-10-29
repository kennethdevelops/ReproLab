import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiGet } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import type { InvestigationSummary, Project } from '../types/api'

export function HomePage() {
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/api/v1/projects'),
  })

  const history = useQuery({
    queryKey: ['investigations'],
    queryFn: () => apiGet<InvestigationSummary[]>('/api/v1/investigations?limit=10'),
  })

  return (
    <div className="space-y-8">
      <section aria-labelledby="projects-heading">
        <h1 id="projects-heading" className="mb-4 text-xl font-semibold">
          Projects
        </h1>
        {projects.isPending && <LoadingBlock label="projects" />}
        {projects.isError && <ErrorBlock error={projects.error} />}
        {projects.data?.length === 0 && (
          <p className="text-sm text-slate-500">
            No projects yet. Run <code className="font-mono">make seed</code> to load the demo
            project.
          </p>
        )}
        <ul className="grid gap-4 md:grid-cols-2">
          {projects.data?.map((project) => (
            <li
              key={project.id}
              className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-medium">{project.name}</h2>
                <span className="font-mono text-xs text-slate-500">{project.mode}</span>
              </div>
              {project.description && (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  {project.description}
                </p>
              )}
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <dt className="text-slate-500">Target</dt>
                <dd className="font-mono">{project.test_origin}</dd>
                <dt className="text-slate-500">Index</dt>
                <dd>
                  {project.current_snapshot ? (
                    <span className="font-mono">
                      <StatusBadge status={project.current_snapshot.status} />{' '}
                      {project.current_snapshot.commit_sha.slice(0, 12)}
                    </span>
                  ) : (
                    <span className="text-slate-500">not indexed</span>
                  )}
                </dd>
              </dl>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="history-heading">
        <h2 id="history-heading" className="mb-3 text-lg font-semibold">
          Recent investigations
        </h2>
        {history.isError && <ErrorBlock error={history.error} />}
        {history.data?.length === 0 && (
          <p className="text-sm text-slate-500">
            None yet.{' '}
            <Link className="text-sky-700 underline dark:text-sky-400" to="/investigate">
              Start one
            </Link>
            .
          </p>
        )}
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900">
          {history.data?.map((inv) => (
            <li key={inv.id}>
              <Link
                to={`/investigations/${inv.id}`}
                className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <StatusBadge status={inv.status} />
                <span className="min-w-0 flex-1 truncate">{inv.bug_report}</span>
                <time
                  className="shrink-0 font-mono text-xs text-slate-500"
                  dateTime={inv.created_at}
                >
                  {new Date(inv.created_at).toLocaleString()}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
