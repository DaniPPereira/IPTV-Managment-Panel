import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Paginated, type Subscription } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { Card, PageHeader, StatusBadge } from '@/components/ui'

export function SubscriptionsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: async () => (await api.get<Paginated<Subscription>>('/api/admin/subscriptions')).data,
  })

  return (
    <div>
      <PageHeader title="Subscriptions" subtitle="Histórico e estado das subscrições" />
      <Card className="overflow-x-auto p-0">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Xtream user</th>
              <th className="px-4 py-3">Expira</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Max devices</th>
              <th className="px-4 py-3">Cliente</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-slate-400">
                  A carregar…
                </td>
              </tr>
            ) : null}
            {data?.items.map((s) => (
              <tr key={s.id} className="border-b border-slate-800/80">
                <td className="px-4 py-3">{s.xtream_username}</td>
                <td className="px-4 py-3">{formatDate(s.expires_at)}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={s.status} />
                </td>
                <td className="px-4 py-3">{s.max_devices}</td>
                <td className="px-4 py-3">
                  <Link className="text-teal-300 hover:underline" to={`/clients/${s.client_id}`}>
                    Abrir cliente
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
