import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './context/AuthContext'
import { SettingsProvider } from './context/SettingsContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Tags from './pages/Tags'
import Trend from './pages/Trend'
import Reports from './pages/Reports'
import AdvancedReports from './pages/AdvancedReports'
import ExcelTemplates from './pages/ExcelTemplates'
import PlcConfig from './pages/PlcConfig'
import Metrics from './pages/Metrics'
import Settings from './pages/Settings'
import './index.css'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 10000, retry: 1 } } })

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">Yükleniyor...</div>
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <SettingsProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
              <Route index element={<Dashboard />} />
              <Route path="tags" element={<Tags />} />
              <Route path="trend" element={<Trend />} />
              <Route path="reports" element={<Reports />} />
              <Route path="advanced-reports" element={<AdvancedReports />} />
              <Route path="excel-templates" element={<ExcelTemplates />} />
              <Route path="plc" element={<PlcConfig />} />
              <Route path="metrics" element={<Metrics />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Routes>
        </BrowserRouter>
        </SettingsProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
