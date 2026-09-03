import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type AdminMe } from '@/lib/api'
import { AdminLayout } from '@/components/AdminLayout'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { ClientsPage } from '@/pages/ClientsPage'
import { ClientCreatePage } from '@/pages/ClientCreatePage'
import { ClientDetailPage } from '@/pages/ClientDetailPage'
import { SubscriptionsPage } from '@/pages/SubscriptionsPage'
import { DevicesPage } from '@/pages/DevicesPage'
import { AuditPage } from '@/pages/AuditPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SetupPage } from '@/pages/SetupPage'

function RequireAuth() {
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => (await api.get<AdminMe>('/api/admin/auth/me')).data,
    retry: false,
  })

  if (me.isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-300">A carregar…</div>
  }
  if (me.isError) return <Navigate to="/admin/login" replace />
  return <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route path="/admin/login" element={<LoginPage />} />
      <Route path="/setup/:token" element={<SetupPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AdminLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/new" element={<ClientCreatePage />} />
          <Route path="/clients/:id" element={<ClientDetailPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/devices" element={<DevicesPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
