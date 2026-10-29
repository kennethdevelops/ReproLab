import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { API_BASE_URL, apiGet } from '../api/client'
import { TERMINAL_STATUSES, type InvestigationDetail } from '../types/api'

export function isTerminal(status: string | undefined): boolean {
  return !!status && (TERMINAL_STATUSES as readonly string[]).includes(status)
}

/**
 * Investigation detail backed by the persisted API record. A server-sent event stream only
 * triggers refetches, so a reload or reconnect always reconstructs the full state from the DB.
 */
export function useInvestigation(id: string) {
  const queryClient = useQueryClient()
  const [live, setLive] = useState(false)

  const query = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => apiGet<InvestigationDetail>(`/api/v1/investigations/${id}`),
    // Polling fallback in case EventSource is blocked by a proxy.
    refetchInterval: (q) => (isTerminal(q.state.data?.status) ? false : 4000),
  })

  const terminal = isTerminal(query.data?.status)

  useEffect(() => {
    if (terminal || typeof EventSource === 'undefined') return
    const source = new EventSource(`${API_BASE_URL}/api/v1/investigations/${id}/events`)
    const refresh = () => void queryClient.invalidateQueries({ queryKey: ['investigation', id] })
    source.onopen = () => setLive(true)
    source.onerror = () => setLive(false)
    for (const type of [
      'investigation.started',
      'browser.action_completed',
      'evidence.created',
      'investigation.budget_warning',
      'investigation.completed',
      'investigation.failed',
      'investigation.cancelled',
    ]) {
      source.addEventListener(type, refresh)
    }
    source.addEventListener('stream.end', () => {
      refresh()
      source.close()
      setLive(false)
    })
    return () => {
      source.close()
      setLive(false)
    }
  }, [id, terminal, queryClient])

  return { ...query, live }
}
