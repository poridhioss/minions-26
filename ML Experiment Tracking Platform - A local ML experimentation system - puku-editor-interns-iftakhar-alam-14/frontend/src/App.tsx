import { Routes, Route, Outlet } from 'react-router-dom'

import Layout from './components/Layout'
import ApiKeyGuard from './components/ApiKeyGuard'
import DashboardPage from './pages/DashboardPage'
import ExperimentsListPage from './pages/ExperimentsListPage'
import ExperimentDetailPage from './pages/ExperimentDetailPage'
import RunDetailPage from './pages/RunDetailPage'
import ModelsPage from './pages/ModelsPage'
import PredictionPlaygroundPage from './pages/PredictionPlaygroundPage'
import SettingsPage from './pages/SettingsPage'
import NotFoundPage from './pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Settings is always reachable so the user can set/clear their API key */}
        <Route path="/settings" element={<SettingsPage />} />

        {/* Everything else is gated behind an API key */}
        <Route element={<ApiKeyGuard><ProtectedShell /></ApiKeyGuard>}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/experiments" element={<ExperimentsListPage />} />
          <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          <Route path="/experiments/:experimentId/runs/:runId" element={<RunDetailPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/playground" element={<PredictionPlaygroundPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

// Just a pass-through that re-emits the layout's <Outlet />.
function ProtectedShell() { return <Outlet /> }
