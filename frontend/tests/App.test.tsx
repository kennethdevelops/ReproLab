import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
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

afterEach(() => vi.unstubAllGlobals())

test('lists projects from the API', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      jsonResponse([
        {
          id: '1',
          name: 'Demo Store',
          description: null,
          repo_url: null,
          repo_ref: null,
          test_origin: 'http://demo-target:4173',
          mode: 'demo',
          created_at: '2026-10-28T00:00:00Z',
          current_snapshot: null,
        },
      ]),
    ),
  )
  renderAt('/')
  expect(await screen.findByText('Demo Store')).toBeInTheDocument()
  expect(screen.getByText('not indexed')).toBeInTheDocument()
})

test('shows API error envelope message', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error: { code: 'INTERNAL_ERROR', message: 'Boom', request_id: 'r1' } }, 500),
      ),
  )
  renderAt('/')
  expect(await screen.findByRole('alert')).toHaveTextContent('Boom (INTERNAL_ERROR)')
})
