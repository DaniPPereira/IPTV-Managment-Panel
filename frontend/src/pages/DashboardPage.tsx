import { useQuery } from '@tanstack/react-query'
import { api, type DashboardStats } from '@/lib/api'
import { Card, PageHeader } from '@/components/ui'

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <div className="text-sm text-slate-400">{label}</div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-slate-50">{value}</div>
    </Card>
  )
}

export function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardStats>('/api/admin/dashboard')).data,
  })

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Visão geral de clientes, subscrições e dispositivos" />
      {isLoading ? <p className="text-slate-400">A carregar…</p> : null}
      {error ? <p className="text-red-300">Não foi possível carregar o dashboard.</p> : null}
      {data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Stat label="Clientes" value={data.clients.total} />
          <Stat label="Ativos" value={data.clients.active} />
          <Stat label="Desativados" value={data.clients.disabled} />
          <Stat label="Subscriptions ativas" value={data.subscriptions.active} />
          <Stat label="Expirados" value={data.subscriptions.expired} />
          <Stat label="Expiram 7 dias" value={data.subscriptions.expiring_7_days} />
          <Stat label="Expiram 30 dias" value={data.subscriptions.expiring_30_days} />
          <Stat label="Dispositivos" value={data.devices.total} />
          <Stat label="Dispositivos ativos" value={data.devices.active} />
        </div>
      ) : null}
    </div>
  )
}
