/**
 * Axios-based API client.
 *
 * One instance for the whole app, configured with:
 *   - baseURL = '' (relative — uses Vite's dev proxy or nginx's path-rewrite in prod)
 *   - X-API-Key header pulled from localStorage on every request
 *   - JSON content type by default
 *   - A response interceptor that surfaces backend error messages as thrown Errors
 */
import axios, { AxiosError, type AxiosInstance } from 'axios'
import toast from 'react-hot-toast'

import type {
  Experiment,
  ExperimentCreate,
  ExperimentUpdate,
  HealthResponse,
  ParameterIn,
  MetricIn,
  FinishRunIn,
  PredictRequest,
  PredictResponse,
  RegisteredModel,
  RegisteredModelVersion,
  Run,
  RunCreate,
  RunUpdate,
} from './types'

const API_KEY_STORAGE = 'mltracker.apiKey'

/** Read the API key from localStorage. Empty string if not set. */
export function getApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE) ?? ''
  } catch {
    return ''
  }
}

/** Persist the API key. */
export function setApiKey(key: string): void {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE, key)
    else localStorage.removeItem(API_KEY_STORAGE)
  } catch {
    /* localStorage unavailable (private mode, etc) — fail silently */
  }
}

const http: AxiosInstance = axios.create({
  baseURL: '',                // same-origin (nginx or vite proxy)
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach the API key on every request.
http.interceptors.request.use((config) => {
  const key = getApiKey()
  if (key) {
    config.headers = config.headers ?? {}
    config.headers['X-API-Key'] = key
  }
  return config
})

// Surface backend error details as toasts.
http.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ detail?: string | unknown[] }>) => {
    // 401 → nudge the user to the settings page
    if (err.response?.status === 401) {
      toast.error('Invalid or missing API key. Open Settings to set one.')
    } else if (err.response?.status === 404) {
      // 404s are often expected (e.g. "no version in that stage"); let
      // the caller decide whether to show a toast.
    } else if (err.response?.data?.detail) {
      const detail = err.response.data.detail
      const message = typeof detail === 'string' ? detail : JSON.stringify(detail)
      toast.error(message)
    } else if (err.message) {
      toast.error(`Network error: ${err.message}`)
    }
    return Promise.reject(err)
  }
)

// ─── Helper: throw on 404 so callers can use `try/catch` ────────────────
async function unwrap<T>(p: Promise<{ data: T }>): Promise<T> {
  const { data } = await p
  return data
}

// ════════════════════════════════════════════════════════════════════════
//  Endpoints
// ════════════════════════════════════════════════════════════════════════

// ─── Health ────────────────────────────────────────────────────────────
export const healthApi = {
  get: () => unwrap<HealthResponse>(http.get<HealthResponse>('/health')),
}

// ─── Experiments ───────────────────────────────────────────────────────
export const experimentsApi = {
  list: (params?: { skip?: number; limit?: number; search?: string }) =>
    unwrap<Experiment[]>(http.get<Experiment[]>('/api/v1/experiments/', { params })),

  count: () => unwrap<number>(http.get<number>('/api/v1/experiments/count')),

  get: (id: number) => unwrap<Experiment>(http.get<Experiment>(`/api/v1/experiments/${id}`)),

  create: (payload: ExperimentCreate) =>
    unwrap<Experiment>(http.post<Experiment>('/api/v1/experiments/', payload)),

  update: (id: number, payload: ExperimentUpdate) =>
    unwrap<Experiment>(http.patch<Experiment>(`/api/v1/experiments/${id}`, payload)),

  delete: async (id: number): Promise<void> => {
    await http.delete(`/api/v1/experiments/${id}`)
  },
}

// ─── Runs ──────────────────────────────────────────────────────────────
export const runsApi = {
  list: (params?: {
    experiment_id?: number
    status?: string
    skip?: number
    limit?: number
  }) => unwrap<Run[]>(http.get<Run[]>('/api/v1/runs/', { params })),

  listForExperiment: (experimentId: number, skip = 0, limit = 100) =>
    unwrap<Run[]>(http.get<Run[]>('/api/v1/runs/', {
      params: { experiment_id: experimentId, skip, limit },
    })),

  count: (experiment_id?: number) =>
    unwrap<number>(http.get<number>('/api/v1/runs/count', { params: { experiment_id } })),

  get: (id: number) => unwrap<Run>(http.get<Run>(`/api/v1/runs/${id}`)),

  create: (payload: RunCreate) =>
    unwrap<Run>(http.post<Run>('/api/v1/runs/', payload)),

  update: (id: number, payload: RunUpdate) =>
    unwrap<Run>(http.patch<Run>(`/api/v1/runs/${id}`, payload)),

  delete: async (id: number): Promise<void> => {
    await http.delete(`/api/v1/runs/${id}`)
  },

  logMetric: (id: number, body: MetricIn) =>
    unwrap<Run>(http.post<Run>(`/api/v1/runs/${id}/metrics`, body)),

  logParameter: (id: number, body: ParameterIn) =>
    unwrap<Run>(http.post<Run>(`/api/v1/runs/${id}/parameters`, body)),

  finish: (id: number, body: FinishRunIn = {}) =>
    unwrap<Run>(http.post<Run>(`/api/v1/runs/${id}/finish`, body)),
}

// ─── Registered models (MLflow registry proxy) ────────────────────────
export const modelsApi = {
  list: () => unwrap<RegisteredModel[]>(http.get<RegisteredModel[]>('/api/v1/models/')),

  versions: (name: string) =>
    unwrap<RegisteredModelVersion[]>(http.get<RegisteredModelVersion[]>(`/api/v1/models/${name}`)),

  latest: (name: string, stage = 'Production') =>
    unwrap<RegisteredModelVersion | null>(
      http.get<RegisteredModelVersion | null>(`/api/v1/models/${name}/latest`, {
        params: { stage },
      })
    ),
}

// ─── Predictions ───────────────────────────────────────────────────────
export const predictionsApi = {
  predict: (payload: PredictRequest) =>
    unwrap<PredictResponse>(http.post<PredictResponse>('/api/v1/predictions/predict', payload)),

  available: () =>
    unwrap<RegisteredModel[]>(http.get<RegisteredModel[]>('/api/v1/predictions/models')),
}

export default http
