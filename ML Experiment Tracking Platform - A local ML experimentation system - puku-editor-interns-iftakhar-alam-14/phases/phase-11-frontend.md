# Phase 11 — React Frontend (Vite + TypeScript SPA)

## 🎯 What This Phase Did

Phase 10 shipped a containerised, nginx-routed backend — but no UI to drive it. **Phase 11 builds the missing front half**: a single-page application that talks to the FastAPI backend we finished in Phase 6, all 20 endpoints now reachable through clicks instead of `curl`.

> 🎭 If the project is a restaurant, this phase is the **dining room**. The kitchen (FastAPI) was open for delivery orders (`curl`) since Phase 6, but you couldn't walk in and sit down. Now there are menus, a host, tables, and a way to actually taste the food.

After this phase:

```bash
cd frontend && npm run dev      # → http://localhost:5173
# OR
docker compose up               # → http://localhost   (nginx serves the SPA + proxies /api)
```

---

## 📂 What Was Created

```
frontend/
├── package.json                ← Vite + React 18 + TS 5.6 + axios + recharts + react-hot-toast
├── tsconfig.json               ← Strict mode, @/* alias → src/*
├── tsconfig.node.json
├── vite.config.ts              ← Port 5173, dev-proxy /api → :8000
├── index.html
├── public/favicon.svg
├── .gitignore  .dockerignore
└── src/
    ├── main.tsx                ← <StrictMode> + <BrowserRouter> + <App> + <Toaster>
    ├── App.tsx                 ← <Routes> with Layout → ApiKeyGuard → pages
    ├── index.css               ← Design tokens (dark theme) + global element styles
    ├── api/
    │   ├── client.ts           ← Axios instance + 5 endpoint groups
    │   └── types.ts            ← Hand-written TS mirrors of the Pydantic schemas
    ├── utils/format.ts         ← formatDateTime, formatRelative, formatNumber, flattenDict
    ├── hooks/useAsync.ts       ← Tiny data-fetching hook (data/error/loading/refresh)
    ├── components/
    │   ├── Layout.tsx + .css           ← Sidebar + header shell (220 + 56 px)
    │   ├── ApiKeyGuard.tsx             ← Redirects to /settings when no key in localStorage
    │   ├── StatusBadge.tsx + .css      ← Coloured pill for RUNNING / FINISHED / FAILED
    │   ├── Spinner.tsx                 ← size="sm" | "lg"
    │   ├── EmptyState.tsx
    │   ├── Modal.tsx                   ← Backdrop-click + Escape-close dialog
    │   ├── ConfirmButton.tsx           ← Two-step "click to confirm" delete pattern
    │   ├── MetricChart.tsx             ← Recharts multi-line chart (one series per run)
    │   └── Common.css                  ← .card, .stat-card, .kv-list, .grid, .dialog, …
    └── pages/
        ├── DashboardPage.tsx           ← Stat cards + recent experiments/runs
        ├── ExperimentsListPage.tsx     ← Filter + table + create modal + delete
        ├── ExperimentDetailPage.tsx    ← Header + metric chart + runs table
        ├── RunDetailPage.tsx           ← KV grid + log metric / log parameter dialogs
        ├── ModelsPage.tsx              ← Split: model list ↔ version table
        ├── PredictionPlaygroundPage.tsx ← Model + stage-or-version + JSON features
        ├── SettingsPage.tsx            ← API key input + /health ping
        └── NotFoundPage.tsx            ← 404 with link back to dashboard
```

27 source files, ~1,500 lines of TypeScript/TSX.

---

## 🏛️ Architecture

```
                  ┌──────────────────────────────────────────────────────────┐
                  │                       Browser                            │
                  │                                                          │
                  │  React 18 SPA (Vite-built, ~640 KB JS)                  │
                  │   │                                                      │
                  │   ├─ <Layout> (sidebar + header + <Outlet />)           │
                  │   │   │                                                  │
                  │   │   └─ <ApiKeyGuard>   (no key ⇒ redirect /settings)  │
                  │   │       │                                              │
                  │   │       ├─ DashboardPage                              │
                  │   │       ├─ ExperimentsListPage                         │
                  │   │       ├─ ExperimentDetailPage                        │
                  │   │       ├─ RunDetailPage                               │
                  │   │       ├─ ModelsPage                                  │
                  │   │       └─ PredictionPlaygroundPage                    │
                  │   │                                                      │
                  │   └─ <SettingsPage>   (always reachable)                 │
                  │                                                          │
                  │  axios  ── X-API-Key (from localStorage) ──────────┐     │
                  └──────────────────────────────────────────────────┼─────┘
                                                                     │
                       dev:    Vite proxy (5173 → 8000)             │
                       prod:   nginx (port 80) ── /api/* ───────────►│
                                                                     ▼
                                                          ┌──────────────────────┐
                                                          │  FastAPI :8000       │
                                                          │  (Phase 6 backend)   │
                                                          └──────────────────────┘
```

### Key decisions

- **Same-origin in both dev and prod.** Vite's dev server proxies `/api`, `/health`, `/docs` to `http://localhost:8000`, and the production nginx config does the same path-rewrite. This means the axios client always uses `baseURL: ''` and the dev/prod code paths are identical.
- **`X-API-Key` is read from `localStorage.mltracker.apiKey`** on every request via an axios request interceptor. No context provider, no React state — keeps the auth model trivial to reason about. The `ApiKeyGuard` component simply checks `getApiKey()` and `<Navigate>`s to `/settings` if it's empty.
- **Hand-written TypeScript types** mirror the Pydantic schemas in `backend/app/schemas/`. The API surface is small (~15 endpoints), so the cost of drift is low and visible in code review. The `PredictRequest` type is intentionally permissive (`features: unknown[] | Record<string, unknown>`) because the backend's `features` field is `Any` in the Pydantic schema — the playground is the place where that flexibility shines.
- **No state management library.** All page state is local (useState), and the `useAsync` hook encapsulates the only cross-cutting concern (loading/error/refresh). When we need it later, we can add a query library (TanStack Query) without rewriting the components — the hook is a drop-in replacement.
- **Dark theme via CSS custom properties** in `src/index.css :root` (no Tailwind, no MUI). Every page uses utility classes (`flex`, `gap-2`, `text-muted`, `mono`) defined in `Common.css`. This keeps the bundle lean (~6 KB of CSS, no runtime CSS-in-JS).
- **Two-step delete confirmation** via `<ConfirmButton>` rather than `window.confirm()` — non-blocking, themeable, and plays nicely with the dark UI.

---

## ⭐ File Tour

### `src/api/client.ts` — The one true HTTP surface

Five endpoint groups, each a plain object of arrow functions:

```typescript
export const experimentsApi = {
  list:   (params?)          => unwrap<Experiment[]>(http.get('/api/v1/experiments/', { params })),
  count:  ()                 => unwrap<number>(http.get('/api/v1/experiments/count')),
  get:    (id)               => unwrap<Experiment>(http.get(`/api/v1/experiments/${id}`)),
  create: (payload)          => unwrap<Experiment>(http.post('/api/v1/experiments/', payload)),
  update: (id, payload)      => unwrap<Experiment>(http.patch(`/api/v1/experiments/${id}`, payload)),
  delete: async (id)         => { await http.delete(`/api/v1/experiments/${id}`) },
}
// …runsApi, modelsApi, predictionsApi, healthApi — same shape
```

- Request interceptor adds `X-API-Key` from `localStorage` on every call.
- Response interceptor turns backend `detail` strings into `react-hot-toast` errors.
- 404s are intentionally **not** auto-toasted — the caller decides (e.g. "latest version of this stage" might 404, and that's OK).

### `src/hooks/useAsync.ts` — 30 lines that replaced a dependency

```typescript
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    let alive = true
    setState(s => ({ ...s, loading: true }))
    fn()
      .then(data => alive && setState({ data, error: null, loading: false }))
      .catch(err => alive && setState({ data: null, error: err as Error, loading: false }))
    return () => { alive = false }
  }, [...deps, tick])

  return { ...state, refresh }
}
```

Used by every page. The `tick` trick means `refresh()` is stable (no stale closures), and the `alive` flag prevents setState-after-unmount warnings.

### `src/components/Layout.tsx` — Sidebar + header + outlet

- 220 px sidebar with brand mark, 5 nav items, and an "API docs →" footer link to `/docs`.
- 56 px header with the page title (auto-derived from `useLocation()`) and a `<HealthIndicator>` that polls `/health` every 15 s and renders a coloured dot (online = green, offline = red, no-key = grey).
- `<Outlet />` renders the routed page.
- Sidebar nav routes: `/`, `/experiments`, `/models`, `/playground`, `/settings`.

### `src/components/MetricChart.tsx` — Recharts multi-line chart

```typescript
// Build "wide" format: one row per (run, step), one column per run
const data = useMemo(() => {
  const rows = new Map<number, Record<string, number | string>>()
  for (const r of runs) {
    const series = r.metrics?.[metricKey]
    if (!series) continue
    for (const [step, value] of Object.entries(series)) {
      const s = Number(step)
      const row = rows.get(s) ?? { _label: s }
      row[String(r.id)] = value
      row._label = s
      rows.set(s, row)
    }
  }
  return [...rows.values()].sort((a, b) => a._label - b._label)
}, [runs, metricKey])
// …one <Line dataKey={String(r.id)} stroke={COLORS[i % COLORS.length]} />
```

Empty state, no animation, 8-color palette. Re-renders cheaply on metric-key change.

### `src/pages/RunDetailPage.tsx` — The most action-rich page

Three dialogs (log metric, log parameter, delete), two state transitions (`Mark finished` / `Mark failed`), and a `KV` helper component that renders label/value pairs from the run's metadata. The `LogMetricModal` parses `key`, `value` (number), `step` and POSTs to `/runs/{id}/metrics`.

### `src/pages/PredictionPlaygroundPage.tsx` — The "what's the API for?" page

A textarea for raw JSON features, a model dropdown, a stage dropdown (Production / Staging / None), and a version dropdown that **overrides** the stage. Sends a `PredictRequest` to `/predictions/predict` and pretty-prints the response.

---

## 🔧 Validation Evidence

### Typecheck

```bash
$ cd frontend && npx tsc --noEmit
# (no output, exit 0)
```

Zero errors after fixing the following classes of issues:

| Class | Files affected | Fix |
|---|---|---|
| Default vs named imports | 7 pages | All components are `export default`; pages were importing as `import { Foo }` — switched to default imports |
| `flattenDict` shape | `RunDetailPage` | Function returns `{ key, value }`; consumers used `.k` / `.v` — fixed |
| `Experiment.tags` access | `DashboardPage` | Field is `string \| null`, not a dict — removed `Object.entries()` and rendered the string as-is |
| `count()` return type | `DashboardPage` | Returns bare `number`, not `{ count, by_status }` — updated StatCard to accept `number \| null` |
| `PredictRequest` field | `PredictionPlaygroundPage` | Field is `features`, not `inputs`; `version` is supported — fixed payload shape |
| `Spinner` prop | 6 pages | Component takes `size="lg"`, not `lg` — fixed all call sites |
| `truncate(null)` | `DashboardPage` | `r.run_name` is `string \| null` — default to `#${r.id}` when null |
| `Layout`/`ApiKeyGuard` import | `App.tsx` | Switched to default imports |
| Health response shape | `SettingsPage` | Backend returns `{ status, app, version, debug }` — used `h.version` not `h.db` |
| Nav route mismatch | `Layout.tsx` | App route is `/playground`, not `/predictions` — fixed nav + title map |

### Build

```bash
$ cd frontend && npm run build
> ml-tracker-frontend@0.1.0 build
> tsc -b && vite build

vite v5.4.21 building for production...
transforming...
✓ 906 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.59 kB │ gzip:   0.36 kB
dist/assets/index-BWj2BqZc.css    6.24 kB │ gzip:   1.84 kB
dist/assets/index-gK3MYRfO.js   639.51 kB │ gzip: 189.35 kB │ map: 2,754.19 kB
✓ built in 4.64s
```

- 906 modules transformed
- 640 KB JS (189 KB gzipped) — bulk is Recharts (~200 KB) and React Router (~50 KB)
- 6 KB CSS (1.8 KB gzipped) — all hand-written, no Tailwind
- Build time: 4.6 s

---

## 🚀 Run It

### Dev mode (hot reload, two terminals)

```bash
# Terminal 1 — backend
cd backend && uvicorn app.main:app --reload
# → http://localhost:8000

# Terminal 2 — frontend
cd frontend && npm run dev
# → http://localhost:5173
```

Vite proxies `/api`, `/health`, `/docs`, `/redoc`, `/openapi.json` to `:8000` automatically.

### Production mode (Docker)

```bash
docker compose up --build
# → http://localhost    (nginx on :80 serves the SPA + proxies /api to the backend container)
```

### Manual smoke test (with the dev API key from `backend/.env`)

1. Open `http://localhost:5173`.
2. You're redirected to `/settings`. Paste the dev API key from `backend/.env` (`API_KEY=...`). Click **Save**, then **Test /health** — the dot in the header should turn green.
3. Go to **Experiments → + New experiment** → name it `iris-baseline` → **Create**. You're back on the list with one row.
4. Click into it → **+ New run** → leave name blank → **Create run**. The run appears in the table.
5. The metric chart area shows "No metrics logged yet" — that's expected; the playground's `Predict` button doesn't log metrics.
6. Go to **Playground**, pick a model, paste `{"feature_0": 1.0}` into the textarea, hit **Predict** — the response renders in the right card.

---

## 📋 What's Next (Phase 12 — Python SDK)

Phase 12 wraps the same 20 endpoints in a tiny Python client, so ML practitioners can:

```python
import mltracker

mltracker.login("https://mltracker.example.com", api_key="...")
exp = mltracker.experiments.create("iris-baseline")
with mltracker.runs(experiment_id=exp.id, name="rf-v1") as run:
    run.log_param("n_estimators", 100)
    for i in range(10):
        run.log_metric("loss", 1.0 / (i + 1), step=i)
```

The SDK will be `pip install mltracker` (or a relative-path `pip install -e sdk/`) and will live in `sdk/mltracker/` (currently empty). The plan:

- **Phase 12a — `client.py`**: thin wrapper around `httpx` with the same 5 endpoint groups as the TS client, plus a `MLTrackerClient` context manager that reads `MLTRACKER_URL` and `MLTRACKER_API_KEY` from env.
- **Phase 12b — `runs.py`**: the `Run` context manager that auto-`finish()`es on exit and exposes `log_param` / `log_metric` / `log_artifact`.
- **Phase 12c — `examples/`**: a `train.py` that replaces the inline `requests` calls in `ml/train.py` with the SDK.
- **Phase 12d — `tests/`**: pytest tests that hit the test-client (no live backend needed), mirroring the FastAPI test suite.

---

## 🎉 Summary

| Metric | Value |
|---|---|
| Files created | 27 |
| Lines of TS/TSX | ~1,500 |
| Components | 8 |
| Pages | 8 |
| API endpoint groups | 5 |
| `tsc --noEmit` errors | **0** |
| `vite build` errors | **0** |
| Final bundle (gzip) | 189 KB JS + 1.8 KB CSS |
| Build time | 4.6 s |

The ML Tracker is now a **complete two-tier system**: a FastAPI backend that owns the data, and a React SPA that owns the experience. Run it with `docker compose up` and you get a real product on port 80.

Next session: Phase 12 — Python SDK.
