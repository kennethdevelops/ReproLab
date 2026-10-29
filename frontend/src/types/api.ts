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
  hypotheses: { statement: string; confidence: string; verification: string }[]
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
