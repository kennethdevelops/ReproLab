export interface Snapshot {
  id: string
  commit_sha: string
  ref: string | null
  status: string
  embed_model: string
  indexed_at: string | null
}

export interface Project {
  id: string
  name: string
  description: string | null
  repo_url: string | null
  repo_ref: string | null
  test_origin: string
  mode: string
  created_at: string
  current_snapshot: Snapshot | null
}

export interface Readiness {
  status: 'ready' | 'not_ready'
  checks: Record<string, string>
}

export interface PublicSettings {
  app_mode: string
  llm_provider: string
  llm_model: string
  llm_configured: boolean
  embedding_provider: string
  embedding_model: string
  limits: Record<string, number>
  demo_allowed_origin: string
}
