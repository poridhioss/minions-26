/**
 * TypeScript types that mirror the FastAPI Pydantic schemas.
 *
 * We keep these hand-written rather than generated, because the API
 * surface is small (~15 endpoints) and drift is easy to spot in code
 * review. If the API grows, swap this for `openapi-typescript`.
 */

// ─── Experiments ───────────────────────────────────────────────────────
export interface Experiment {
  id: number
  name: string
  description: string | null
  tags: string | null
  created_at: string          // ISO 8601 datetime
  updated_at: string | null
}

export interface ExperimentCreate {
  name: string
  description?: string | null
  tags?: string | null
}

export interface ExperimentUpdate {
  name?: string
  description?: string | null
  tags?: string | null
}

// ─── Runs ──────────────────────────────────────────────────────────────
export type RunStatus = 'RUNNING' | 'FINISHED' | 'FAILED'

export interface Run {
  id: number
  experiment_id: number
  run_name: string | null
  status: RunStatus | null
  artifact_uri: string | null
  metrics: Record<string, number> | null
  parameters: Record<string, unknown> | null
  tags: Record<string, unknown> | null
  start_time: string
  end_time: string | null
  status_message?: string | null
  user_id?: string | null
}

export interface RunCreate {
  experiment_id: number
  run_name?: string | null
  status?: RunStatus
  artifact_uri?: string | null
  metrics?: Record<string, number> | null
  parameters?: Record<string, unknown> | null
  tags?: Record<string, unknown> | null
}

export interface RunUpdate {
  run_name?: string | null
  status?: RunStatus
  end_time?: string | null
  metrics?: Record<string, number> | null
  parameters?: Record<string, unknown> | null
  tags?: Record<string, unknown> | null
  artifact_uri?: string | null
}

export interface MetricIn {
  key: string
  value: number
  step?: number
}

export interface ParameterIn {
  key: string
  value: string
}

export interface FinishRunIn {
  status?: 'FINISHED' | 'FAILED'
  final_metrics?: Record<string, number> | null
}

// ─── Predictions ───────────────────────────────────────────────────────
export interface PredictRequest {
  model_name?: string
  model_uri?: string
  stage?: 'Production' | 'Staging' | 'Archived' | 'None'
  version?: number | string
  features: unknown[] | Record<string, unknown>
}

export interface PredictResponse {
  predictions: unknown
  model_name?: string
  model_version?: string
  model_stage?: string
}

export interface AvailableModelSummary {
  name: string
  latest_versions?: Array<{
    name: string
    version: string
    stage: string
    run_id?: string
  }>
}

// ─── Registered Models (from /models) ──────────────────────────────────
export type ModelStage = 'Production' | 'Staging' | 'Archived' | 'None'

export interface RegisteredModelVersion {
  name: string
  version: string
  stage: ModelStage
  run_id?: string
  description?: string
  creation_timestamp?: string
  last_updated_timestamp?: string
  current_stage?: string
  created_at?: string
  last_updated?: string
}

export interface RegisteredModel {
  name: string
  description?: string | null
  creation_timestamp?: string
  last_updated_timestamp?: string
  last_updated?: string
  latest_versions: RegisteredModelVersion[]
}

// ─── Health ────────────────────────────────────────────────────────────
export interface HealthResponse {
  status: string
  app: string
  version: string
  [k: string]: unknown
}
