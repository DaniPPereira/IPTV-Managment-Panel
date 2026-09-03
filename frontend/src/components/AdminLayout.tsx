import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LayoutDashboard, Users, CreditCard, Smartphone, ScrollText, Settings, LogOut } from 'lucide-react'
import { api, type AdminMe } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/clients', label: 'Clients', icon: Users },
  { to: '/subscriptions', label: 'Subscriptions', icon: CreditCard },
  { to: '/devices', label: 'Devices', icon: Smartphone },
  { to: '/audit', label: 'Audit Log', icon: ScrollText },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AdminLayout() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => (await api.get<AdminMe>('/api/admin/auth/me')).data,
  })

  const logout = useMutation({
    mutationFn: async () => api.post('/api/admin/auth/logout'),
    onSuccess: () => {
      qc.clear()
      navigate('/admin/login')
    },
  })

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-slate-800 bg-slate-950/70 lg:border-b-0 lg:border-r">
        <div className="px-5 py-5">
          <div className="text-xs uppercase tracking-[0.2em] text-teal-300/80">IPTV Panel</div>
          <div className="mt-1 text-lg font-semibold text-slate-50">Provisioning</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-4 lg:flex-col">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-300 hover:bg-slate-800/80',
                  isActive && 'bg-slate-800 text-teal-300',
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3 sm:px-6">
          <div className="text-sm text-slate-400">Gestão de clientes e acessos</div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-200">{me.data?.username || 'Admin'}</span>
            <Button variant="ghost" onClick={() => logout.mutate()}>
              <LogOut size={16} />
              Logout
            </Button>
          </div>
        </header>
        {me.data?.must_change_password ? (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-200 sm:px-6">
            Change initial administrator password.
          </div>
        ) : null}
        <main className="px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
