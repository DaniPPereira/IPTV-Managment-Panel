import { useQuery } from '@tanstack/react-query'
import { api, type AuditLog, type Paginated } from '@/lib/api'
import { Card, PageHeader } from '@/components/ui'

export function AuditPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['audit'],
    queryFn: async () => (await api.get<Paginated<AuditLog>>('/api/admin/audit-logs')).data,
  })

  return (
    <div>
      <PageHeader title="Audit Log" subtitle="Ações administrativas recentes" />
      <Card className="overflow-x-auto p-0">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Quando</th>
              <th className="px-4 py-3">Ação</th>
              <th className="px-4 py-3">Entidade</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Detalhes</th>
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
            {data?.items.map((row) => (
              <tr key={row.id} className="border-b border-slate-800/80">
                <td className="px-4 py-3 whitespace-nowrap">{new Date(row.created_at).toLocaleString('pt-PT')}</td>
                <td className="px-4 py-3">{row.action}</td>
                <td className="px-4 py-3">
                  {row.entity_type}
                  {row.entity_id ? ` · ${row.entity_id.slice(0, 8)}` : ''}
                </td>
                <td className="px-4 py-3">{row.ip_address || '—'}</td>
                <td className="px-4 py-3 max-w-xs truncate text-slate-400">{row.details || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
