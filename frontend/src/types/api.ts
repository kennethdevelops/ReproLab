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

export interface IndexStatus {
  id: string
  commit_sha: string
  ref: string | null
  source_kind: string
  status: string
  embed_model: string
  embed_dim: number | null
  parser_version: string
  progress: Record<string, unknown>
  error: string | null
  citation_base_url: string | null
  created_at: string
  indexed_at: string | null
}

export type SearchStrategy = 'lexical' | 'vector' | 'hybrid'

export interface SearchHit {
  chunk_id: string
  path: string
  kind: string
  start_line: number
  end_line: number
  symbol: string | null
  excerpt: string
  score: number
  ranks: Partial<Record<'lexical' | 'vector', number>>
  citation_url: string | null
}

export interface SearchResponse {
  snapshot_id: string
  commit_sha: string
  strategy: SearchStrategy
  query: string
  timing_ms: number
  hits: SearchHit[]
}

export interface SourceExcerpt {
  path: string
  start_line: number
  end_line: number
  total_lines: number
  content: string
  commit_sha: string
}

export interface Readiness {
  status: 'ready' | 'not_ready'
  checks: Record<string, string>
}

export interface PublicSettings {
  app_mode: string
  llm_provider: string
  llm_model: string
  llm_base_url?: string | null
  llm_configured: boolean
  embedding_provider: string
  embedding_model: string
  limits: Record<string, number>
  demo_allowed_origin: string
}

export interface DemoCase {
  case_id: string
  title: string
  bug_report: string
  start_path: string
}

export const TERMINAL_STATUSES = [
  'reproduced',
  'not_reproduced',
  'blocked',
  'inconclusive',
  'cancelled',
  'failed',
] as const

export interface InvestigationSummary {
  id: string
  project_id: string
  bug_report: string
  start_path: string
  status: string
  status_reason: string | null
  rag_mode: string
  model_id: string
  limits: Record<string, number>
  usage: Record<string, number | null>
  cancel_requested: boolean
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: InvestigationResult | null
}

export interface Step {
  sequence: number
  node: string
  tool: string | null
  redacted_input: Record<string, unknown>
  output_summary: string | null
  ok: boolean
  time_ms: number
  usage: Record<string, unknown>
  created_at: string
}

export interface Evidence {
  id: string
  type: string
  label: string
  mime_type: string
  sha256: string
  size: number
  step_sequence: number | null
  created_at: string
}

export interface Finding {
  id: string
  type: string
  statement: string
  verification_status: string
}

export interface InvestigationResult {
  status: string
  status_reason: string
  claimed_status: string | null
  verification: {
    level: string
    notes: string[]
    verified_evidence: { step: number; tool: string; quote: string }[]
  }
  expected_behaviour: string | null
  observed_behaviour: string | null
  reproduction_steps: string[]
  hypotheses: {
    statement: string
    confidence: string
    verification: string
    citations?: string[]
  }[]
  regression_test?: RegressionTest | null
  run: {
    model_id: string
    model_calls: number
    browser_steps: number
    usage: Record<string, number>
    estimated_cost_usd: number | null
    browser_version: string
    viewport: { width: number; height: number }
  }
}

export interface InvestigationDetail extends InvestigationSummary {
  steps: Step[]
  evidence: Evidence[]
  findings: Finding[]
}

export interface RegressionRun {
  started: string
  finished: string
  outcome: 'passed' | 'assertion_failed' | 'setup_failed' | 'error'
  failing_step: string | null
  message: string
}

export interface RegressionTest {
  status: 'validated' | 'invalid' | 'unvalidated' | 'not_generated'
  reason: string
  spec: Record<string, unknown> | null
  code: string | null
  validation: { buggy?: RegressionRun; fixed?: RegressionRun; errors?: string[] } | null
}
