import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Device, type Paginated } from '@/lib/api'
import { formatRelative } from '@/lib/utils'
import { Card, Input, PageHeader } from '@/components/ui'

export function DevicesPage() {
  const [search, setSearch] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['devices', search],
    queryFn: async () =>
      (
        await api.get<Paginated<Device>>('/api/admin/devices', {
          params: { search: search || undefined },
        })
      ).data,
  })

  return (
    <div>
      <PageHeader title="Devices" subtitle="Dispositivos associados a clientes" />
      <Card className="mb-4">
        <Input
          placeholder="Pesquisar nome, MAC ou identifier…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </Card>
      <Card className="overflow-x-auto p-0">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Nome</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">MAC</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Último visto</th>
              <th className="px-4 py-3">Cliente</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-slate-400">
                  A carregar…
                </td>
              </tr>
            ) : null}
            {data?.items.map((d) => (
              <tr key={d.id} className="border-b border-slate-800/80">
                <td className="px-4 py-3">{d.name}</td>
                <td className="px-4 py-3">{d.device_type}</td>
                <td className="px-4 py-3">{d.mac_address || '—'}</td>
                <td className="px-4 py-3">{d.active ? 'Ativo' : 'Inativo'}</td>
                <td className="px-4 py-3">{formatRelative(d.last_seen_at)}</td>
                <td className="px-4 py-3">
                  <Link className="text-teal-300 hover:underline" to={`/clients/${d.client_id}`}>
                    Abrir
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
