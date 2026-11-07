import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { apiGet, apiPost } from '../api/client'
import { ErrorBlock, LoadingBlock } from '../components/QueryState'
import { StatusBadge } from '../components/StatusBadge'
import type {
  IndexStatus,
  Project,
  SearchHit,
  SearchResponse,
  SearchStrategy,
  SourceExcerpt,
} from '../types/api'

const STRATEGIES: SearchStrategy[] = ['lexical', 'vector', 'hybrid']
type Mode = SearchStrategy | 'compare'
const KINDS = ['source', 'test', 'documentation', 'configuration'] as const
const IN_PROGRESS = new Set(['pending', 'fetching', 'parsing', 'embedding'])

/** Progress values are counts, strings, or count maps such as `excluded: {reason: n}`. */
function formatProgress(value: unknown): string {
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    return entries.length
      ? entries.map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(', ')
      : '0'
  }
  return String(value)
}

interface Search {
  projectId: string
  q: string
  strategies: SearchStrategy[]
  kind: string
  topK: number
}

function searchUrl(s: Search, strategy: SearchStrategy): string {
  const params = new URLSearchParams({ q: s.q, strategy, top_k: String(s.topK) })
  if (s.kind) params.append('kind', s.kind)
  return `/api/v1/projects/${s.projectId}/search?${params}`
}

function IndexPanel({ projectId }: { projectId: string }) {
  const client = useQueryClient()
  const status = useQuery({
    queryKey: ['index', projectId],
    queryFn: () => apiGet<IndexStatus[]>(`/api/v1/projects/${projectId}/index`),
    refetchInterval: (query) =>
      query.state.data?.some((s) => IN_PROGRESS.has(s.status)) ? 1500 : false,
  })
  const start = useMutation({
    mutationFn: () => apiPost(`/api/v1/projects/${projectId}/index`),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['index', projectId] })
      void client.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const latest = status.data?.[0]

  return (
    <section
      aria-labelledby="index-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="index-heading" className="font-medium">
          Repository index
        </h2>
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {start.isPending ? 'Starting…' : 'Index now'}
        </button>
      </div>
      {status.isPending && <LoadingBlock label="index status" />}
      {status.isError && <ErrorBlock error={status.error} />}
      {start.isError && <ErrorBlock error={start.error} />}
      {status.data?.length === 0 && <p className="mt-2 text-slate-500">Not indexed yet.</p>}
      {latest && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          <dt className="text-slate-500">Status</dt>
          <dd>
            <StatusBadge status={latest.status} />
            {latest.error && <span className="ml-2 text-red-700">{latest.error}</span>}
          </dd>
          <dt className="text-slate-500">Commit</dt>
          <dd className="font-mono">{latest.commit_sha.slice(0, 12)}</dd>
          <dt className="text-slate-500">Embeddings</dt>
          <dd className="font-mono">
            {latest.embed_model}
            {latest.embed_dim ? ` (${latest.embed_dim}d)` : ''}
          </dd>
          <dt className="text-slate-500">Chunker</dt>
          <dd className="font-mono">{latest.parser_version}</dd>
          {Object.entries(latest.progress)
            .filter(([name]) => name !== 'chunker')
            .map(([name, value]) => (
              <div key={name} className="contents">
                <dt className="text-slate-500">{name.replace(/_/g, ' ')}</dt>
                <dd className="font-mono">{formatProgress(value)}</dd>
              </div>
            ))}
        </dl>
      )}
    </section>
  )
}

function HitList({
  hits,
  selected,
  onSelect,
}: {
  hits: SearchHit[]
  selected: string | null
  onSelect: (hit: SearchHit) => void
}) {
  if (hits.length === 0) return <p className="text-sm text-slate-500">No matches.</p>
  return (
    <ol className="space-y-2">
      {hits.map((hit, i) => (
        <li key={hit.chunk_id}>
          <button
            type="button"
            onClick={() => onSelect(hit)}
            aria-pressed={selected === hit.chunk_id}
            className={`w-full rounded border p-2 text-left text-xs hover:bg-slate-50 dark:hover:bg-slate-800 ${
              selected === hit.chunk_id
                ? 'border-sky-500'
                : 'border-slate-200 dark:border-slate-800'
            }`}
          >
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-slate-500">#{i + 1}</span>
              <span className="font-mono font-medium break-all">
                {hit.path}:{hit.start_line}-{hit.end_line}
              </span>
              {hit.symbol && <span className="font-mono text-sky-700">{hit.symbol}</span>}
              <span className="text-slate-500">{hit.kind}</span>
            </div>
            <div className="mt-1 font-mono text-slate-500">
              score {hit.score.toFixed(4)}
              {Object.entries(hit.ranks).map(([name, rank]) => ` · ${name} #${rank}`)}
            </div>
          </button>
        </li>
      ))}
    </ol>
  )
}

function SourceView({ projectId, hit }: { projectId: string; hit: SearchHit }) {
  const params = new URLSearchParams({
    path: hit.path,
    start_line: String(hit.start_line),
    end_line: String(hit.end_line),
  })
  const source = useQuery({
    queryKey: ['source', projectId, hit.chunk_id],
    queryFn: () => apiGet<SourceExcerpt>(`/api/v1/projects/${projectId}/source?${params}`),
  })
  return (
    <section aria-labelledby="source-heading" className="space-y-2">
      <h2 id="source-heading" className="font-mono text-sm font-medium break-all">
        {hit.path}
      </h2>
      {source.isPending && <LoadingBlock label="source" />}
      {source.isError && <ErrorBlock error={source.error} />}
      {source.data && (
        <>
          <p className="text-xs text-slate-500">
            Lines {source.data.start_line}–{source.data.end_line} of {source.data.total_lines} at{' '}
            <span className="font-mono">{source.data.commit_sha.slice(0, 12)}</span>
            {hit.citation_url && (
              <>
                {' · '}
                <a className="text-sky-700 underline" href={hit.citation_url}>
                  view upstream
                </a>
              </>
            )}
          </p>
          <pre className="overflow-x-auto rounded border border-slate-200 bg-slate-50 p-2 text-xs dark:border-slate-800 dark:bg-slate-950">
            {source.data.content.split('\n').map((line, i) => (
              <div key={i}>
                <span className="mr-3 inline-block w-8 text-right text-slate-400 select-none">
                  {source.data.start_line + i}
                </span>
                {line}
              </div>
            ))}
          </pre>
        </>
      )}
    </section>
  )
}

function ResultColumn({
  search,
  strategy,
  selected,
  onSelect,
}: {
  search: Search
  strategy: SearchStrategy
  selected: string | null
  onSelect: (hit: SearchHit) => void
}) {
  const result = useQuery({
    queryKey: ['search', search, strategy],
    queryFn: () => apiGet<SearchResponse>(searchUrl(search, strategy)),
  })
  return (
    <section aria-label={`${strategy} results`} className="min-w-0 space-y-2">
      <h2 className="text-sm font-medium">
        {strategy}
        {result.data && (
          <span className="ml-2 font-mono text-xs text-slate-500">{result.data.timing_ms} ms</span>
        )}
      </h2>
      {result.isPending && <LoadingBlock label={`${strategy} results`} />}
      {result.isError && <ErrorBlock error={result.error} />}
      {result.data && <HitList hits={result.data.hits} selected={selected} onSelect={onSelect} />}
    </section>
  )
}

export function RagExplorerPage() {
  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/api/v1/projects'),
  })
  const [projectId, setProjectId] = useState('')
  const [q, setQ] = useState('')
  const [mode, setMode] = useState<Mode>('hybrid')
  const [kind, setKind] = useState('')
  const [topK, setTopK] = useState(6)
  const [search, setSearch] = useState<Search | null>(null)
  const [selected, setSelected] = useState<SearchHit | null>(null)

  const activeProject = projectId || projects.data?.[0]?.id || ''

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!activeProject || !q.trim()) return
    setSelected(null)
    setSearch({
      projectId: activeProject,
      q: q.trim(),
      strategies: mode === 'compare' ? STRATEGIES : [mode],
      kind,
      topK,
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">RAG Explorer</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Query the repository index the agent uses. Hybrid fuses lexical and vector rankings with
          Reciprocal Rank Fusion (k = 60).
        </p>
      </div>

      {projects.isPending && <LoadingBlock label="projects" />}
      {projects.isError && <ErrorBlock error={projects.error} />}
      {projects.data?.length === 0 && <p className="text-sm text-slate-500">No projects yet.</p>}

      {activeProject && (
        <>
          <label className="block text-sm">
            <span className="mr-2 text-slate-500">Project</span>
            <select
              value={activeProject}
              onChange={(e) => {
                setProjectId(e.target.value)
                setSearch(null)
                setSelected(null)
              }}
              className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
            >
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>

          <IndexPanel projectId={activeProject} />

          <form onSubmit={submit} className="flex flex-wrap items-end gap-3 text-sm">
            <label className="flex min-w-64 flex-1 flex-col gap-1">
              <span className="text-slate-500">Query</span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="coupon removed on checkout refresh"
                maxLength={500}
                className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Strategy</span>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as Mode)}
                className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
              >
                {STRATEGIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
                <option value="compare">compare all</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Kind</span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="">any</option>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Top k</span>
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
                className="w-20 rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
            <button
              type="submit"
              className="rounded bg-slate-900 px-4 py-1.5 text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900"
            >
              Search
            </button>
          </form>

          {search && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className={`grid gap-4 ${search.strategies.length > 1 ? 'sm:grid-cols-3' : ''}`}>
                {search.strategies.map((s) => (
                  <ResultColumn
                    key={s}
                    search={search}
                    strategy={s}
                    selected={selected?.chunk_id ?? null}
                    onSelect={setSelected}
                  />
                ))}
              </div>
              {selected ? (
                <SourceView projectId={search.projectId} hit={selected} />
              ) : (
                <p className="text-sm text-slate-500">Select a result to read its source lines.</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
