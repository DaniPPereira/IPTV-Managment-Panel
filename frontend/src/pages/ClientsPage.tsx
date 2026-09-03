import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, type ClientListItem, type Paginated } from '@/lib/api'
import { formatDate, formatRelative } from '@/lib/utils'
import { Button, Card, Input, PageHeader, Select, StatusBadge } from '@/components/ui'

const filters = [
  { value: '', label: 'Todos' },
  { value: 'active', label: 'Ativos' },
  { value: 'expired', label: 'Expirados' },
  { value: 'expiring_7', label: 'Expiram em 7 dias' },
  { value: 'expiring_30', label: 'Expiram em 30 dias' },
  { value: 'disabled', label: 'Desativados' },
]

export function ClientsPage() {
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') || 1)
  const search = params.get('search') || ''
  const status = params.get('status') || ''

  const { data, isLoading } = useQuery({
    queryKey: ['clients', page, search, status],
    queryFn: async () =>
      (
        await api.get<Paginated<ClientListItem>>('/api/admin/clients', {
          params: { page, page_size: 25, search: search || undefined, status: status || undefined },
        })
      ).data,
  })

  return (
    <div>
      <PageHeader
        title="Clients"
        subtitle="Pesquisar, filtrar e gerir clientes"
        actions={
          <Link to="/clients/new">
            <Button>Criar cliente</Button>
          </Link>
        }
      />
      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-[1fr_220px]">
          <Input
            placeholder="Pesquisar nome, email, telefone, MAC, Xtream…"
            defaultValue={search}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const value = (e.target as HTMLInputElement).value
                const next = new URLSearchParams(params)
                next.set('page', '1')
                if (value) next.set('search', value)
                else next.delete('search')
                setParams(next)
              }
            }}
          />
          <Select
            value={status}
            onChange={(e) => {
              const next = new URLSearchParams(params)
              next.set('page', '1')
              if (e.target.value) next.set('status', e.target.value)
              else next.delete('status')
              setParams(next)
            }}
          >
            {filters.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Cliente</th>
              <th className="px-4 py-3">Expira</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Devices</th>
              <th className="px-4 py-3">Último acesso</th>
              <th className="px-4 py-3">Ações</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td className="px-4 py-6 text-slate-400" colSpan={6}>
                  A carregar…
                </td>
              </tr>
            ) : null}
            {data?.items.map((c) => (
              <tr key={c.id} className="border-b border-slate-800/80 hover:bg-slate-800/30">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-100">{c.name}</div>
                  <div className="text-xs text-slate-400">{c.email || c.phone || '—'}</div>
                </td>
                <td className="px-4 py-3">{formatDate(c.expires_at)}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={c.status} />
                </td>
                <td className="px-4 py-3">{c.device_count}</td>
                <td className="px-4 py-3">{formatRelative(c.last_access_at)}</td>
                <td className="px-4 py-3">
                  <Link className="text-teal-300 hover:underline" to={`/clients/${c.id}`}>
                    Abrir
                  </Link>
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-400" colSpan={6}>
                  Nenhum cliente encontrado.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Card>

      {data && data.pages > 1 ? (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
          <span>
            Página {data.page} de {data.pages} · {data.total} total
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => {
                const next = new URLSearchParams(params)
                next.set('page', String(page - 1))
                setParams(next)
              }}
            >
              Anterior
            </Button>
            <Button
              variant="secondary"
              disabled={page >= data.pages}
              onClick={() => {
                const next = new URLSearchParams(params)
                next.set('page', String(page + 1))
                setParams(next)
              }}
            >
              Seguinte
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
