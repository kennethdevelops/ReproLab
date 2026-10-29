import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import type { Project } from '../types/api'

export function HomePage() {
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/api/v1/projects'),
  })

  return (
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
  )
}
