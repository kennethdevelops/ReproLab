import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import App from '../src/App'

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

/** Route fetch calls by URL substring; unmatched URLs fail loudly. */
function mockApi(routes: Record<string, unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const key = Object.keys(routes).find((k) => url.includes(k))
    if (!key) throw new Error(`unmocked ${url}`)
    const value = routes[key]
    return typeof value === 'function'
      ? (value as (i?: RequestInit) => Response)(init)
      : jsonResponse(value)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

const PROJECT = {
  id: 'p1',
  name: 'Demo Store',
  description: null,
  repo_url: null,
  repo_ref: null,
  test_origin: 'http://demo-target:4173',
  mode: 'demo',
  created_at: '2026-10-28T00:00:00Z',
  current_snapshot: null,
}

const SETTINGS = {
  app_mode: 'local',
  llm_provider: 'anthropic',
  llm_model: 'claude-opus-5-5',
  llm_configured: false,
  embedding_provider: 'fastembed',
  embedding_model: 'm',
  limits: {
    max_browser_steps: 25,
    max_model_calls: 30,
    max_investigation_seconds: 300,
    max_run_cost_usd: 1,
    max_bug_report_chars: 4000,
  },
  demo_allowed_origin: 'http://demo-target:4173',
}

afterEach(() => vi.unstubAllGlobals())

test('lists projects and empty history from the API', async () => {
  mockApi({ '/api/v1/projects': [PROJECT], '/api/v1/investigations': [] })
  renderAt('/')
  expect(await screen.findByText('Demo Store')).toBeInTheDocument()
  expect(screen.getByText('not indexed')).toBeInTheDocument()
  expect(await screen.findByText(/None yet/)).toBeInTheDocument()
})

test('shows API error envelope message', async () => {
  mockApi({
    '/api/v1/projects': () =>
      jsonResponse({ error: { code: 'INTERNAL_ERROR', message: 'Boom', request_id: 'r1' } }, 500),
    '/api/v1/investigations': [],
  })
  renderAt('/')
  expect(await screen.findByRole('alert')).toHaveTextContent('Boom (INTERNAL_ERROR)')
})

test('new investigation form loads a demo case, warns about missing key and submits', async () => {
  const fetchMock = mockApi({
    '/api/v1/projects': [PROJECT],
    '/api/v1/demo/cases': [
      {
        case_id: 'D01',
        title: 'Coupon lost',
        bug_report: 'Coupon disappears after reload.',
        start_path: '/shop',
      },
    ],
    '/api/v1/settings': SETTINGS,
    '/api/v1/investigations': () =>
      jsonResponse({ investigation_id: 'inv1', status: 'queued' }, 202),
  })
  renderAt('/investigate')
  await userEvent.click(await screen.findByRole('button', { name: /D01/ }))
  expect(screen.getByLabelText(/^Bug report/)).toHaveValue('Coupon disappears after reload.')
  expect(screen.getByLabelText('Start path')).toHaveValue('/shop')
  expect(await screen.findByText(/No model provider key is configured/)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Run investigation' }))
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(post).toBeDefined()
  const body = JSON.parse(String(post![1]!.body))
  expect(body).toMatchObject({ project_id: 'p1', start_path: '/shop', rag_mode: 'none' })
  expect(body).not.toHaveProperty('test_origin')
})

test('investigation page separates verified evidence from rejected claims and hypotheses', async () => {
  mockApi({
    '/api/v1/investigations/inv1': {
      id: 'inv1',
      project_id: 'p1',
      bug_report: 'Coupon disappears after reload.',
      start_path: '/shop',
      status: 'inconclusive',
      status_reason: 'Compared summaries. [Reproduction claim rejected: quote does not appear]',
      rag_mode: 'none',
      model_id: 'stub',
      limits: {},
      usage: {},
      cancel_requested: false,
      created_at: '2026-10-28T00:00:00Z',
      started_at: null,
      completed_at: '2026-10-28T00:01:00Z',
      result: {
        status: 'inconclusive',
        status_reason: 'x',
        claimed_status: 'reproduced',
        verification: { level: 'none', notes: [], verified_evidence: [] },
        expected_behaviour: 'Discount persists',
        observed_behaviour: 'Discount gone',
        reproduction_steps: ['Open /shop'],
        hypotheses: [
          {
            statement: 'State is memory-only',
            confidence: 'medium',
            verification: 'unverified_hypothesis',
          },
        ],
        run: {
          model_id: 'stub',
          model_calls: 3,
          browser_steps: 5,
          usage: {},
          estimated_cost_usd: 0,
          browser_version: '140',
          viewport: { width: 1365, height: 768 },
        },
      },
      steps: [
        {
          sequence: 1,
          node: 'act',
          tool: 'open_page',
          redacted_input: {},
          output_summary: 'Opened /shop (HTTP 200)',
          ok: true,
          time_ms: 120,
          usage: {},
          created_at: '',
        },
      ],
      evidence: [],
      findings: [],
    },
  })
  renderAt('/investigations/inv1')
  expect(await screen.findByText(/did not\s+pass verification/)).toBeInTheDocument()
  expect(screen.getByText(/Root-cause hypotheses — not verified/)).toBeInTheDocument()
  expect(screen.getByText('Opened /shop (HTTP 200)')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
})
