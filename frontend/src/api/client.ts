export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let code = 'HTTP_ERROR'
  let message = `Request failed with status ${response.status}`
  let requestId = response.headers.get('x-request-id')
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; request_id?: string }
    }
    if (body.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      requestId = body.error.request_id ?? requestId
    }
  } catch {
    // Non-JSON error body; keep the generic message.
  }
  throw new ApiRequestError(response.status, code, message, requestId)
}

export async function apiGet<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`${API_BASE_URL}${path}`))
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}
