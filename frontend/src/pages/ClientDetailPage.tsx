import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { api, type ClientDetail } from '@/lib/api'
import { copyText, formatDate } from '@/lib/utils'
import { Button, Card, Input, Label, PageHeader, Select, StatusBadge, Textarea } from '@/components/ui'

export function ClientDetailPage() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [showM3u, setShowM3u] = useState(false)
  const [showEpg, setShowEpg] = useState(false)
  const [showXtreamPass, setShowXtreamPass] = useState(false)
  const [message, setMessage] = useState('')
  const [deviceForm, setDeviceForm] = useState({ name: '', device_type: 'OTHER', mac_address: '' })

  const { data, isLoading, error } = useQuery({
    queryKey: ['client', id],
    enabled: !!id,
    queryFn: async () => (await api.get<ClientDetail>(`/api/admin/clients/${id}`)).data,
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['client', id] })

  const updateClient = useMutation({
    mutationFn: async (payload: Partial<ClientDetail>) => api.patch(`/api/admin/clients/${id}`, payload),
    onSuccess: () => {
      setMessage('Cliente atualizado')
      refresh()
    },
  })

  const renew = useMutation({
    mutationFn: async (months: number) =>
      api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/renew`, { months }),
    onSuccess: () => {
      setMessage('Subscrição renovada')
      refresh()
    },
  })

  const disableClient = useMutation({
    mutationFn: async () => api.patch(`/api/admin/clients/${id}`, { active: false }),
    onSuccess: () => {
      setMessage('Cliente desativado')
      refresh()
    },
  })

  const regenerateToken = useMutation({
    mutationFn: async () =>
      api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/regenerate-token`),
    onSuccess: () => {
      setMessage('Token regenerado')
      refresh()
    },
  })

  const regenerateXtream = useMutation({
    mutationFn: async () =>
      api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/regenerate-xtream-password`),
    onSuccess: () => {
      setMessage('Password Xtream regenerada')
      refresh()
    },
  })

  const testSource = useMutation({
    mutationFn: async () =>
      (await api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/test-source`)).data,
    onSuccess: (res) => setMessage(`Teste M3U: ${res.m3u?.success ? 'OK' : 'FALHOU'}`),
  })

  const refreshPlaylist = useMutation({
    mutationFn: async () => api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/refresh-playlist`),
    onSuccess: () => setMessage('Playlist refreshed'),
  })

  const refreshEpg = useMutation({
    mutationFn: async () => api.post(`/api/admin/subscriptions/${data?.current_subscription?.id}/refresh-epg`),
    onSuccess: () => setMessage('EPG refreshed'),
  })

  const addDevice = useMutation({
    mutationFn: async () =>
      api.post(`/api/admin/clients/${id}/devices`, {
        name: deviceForm.name,
        device_type: deviceForm.device_type,
        mac_address: deviceForm.mac_address || null,
      }),
    onSuccess: () => {
      setDeviceForm({ name: '', device_type: 'OTHER', mac_address: '' })
      refresh()
    },
  })

  const removeDevice = useMutation({
    mutationFn: async (deviceId: string) => api.delete(`/api/admin/devices/${deviceId}`),
    onSuccess: refresh,
  })

  if (isLoading) return <p className="text-slate-400">A carregar…</p>
  if (error || !data) return <p className="text-red-300">Cliente não encontrado.</p>

  const sub = data.current_subscription

  return (
    <div className="space-y-6">
      <PageHeader
        title={data.name}
        subtitle={data.email || data.phone || undefined}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/clients">
              <Button variant="secondary">Voltar</Button>
            </Link>
            <Button
              variant="danger"
              onClick={() => {
                if (confirm('Tem a certeza?\n\nTodos os acessos M3U, EPG, Xtream e dispositivos associados deixarão imediatamente de funcionar.')) {
                  disableClient.mutate()
                }
              }}
            >
              Desativar
            </Button>
          </div>
        }
      />

      {message ? <p className="text-sm text-teal-300">{message}</p> : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <div className="text-xs uppercase text-slate-400">Estado</div>
          <div className="mt-2">
            <StatusBadge status={data.status} />
          </div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-400">Expira</div>
          <div className="mt-2 text-lg">{formatDate(sub?.expires_at)}</div>
        </Card>
        <Card>
          <div className="text-xs uppercase text-slate-400">Telefone</div>
          <div className="mt-2 text-lg">{data.phone || '—'}</div>
        </Card>
      </div>

      <Card>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-300">Dados do cliente</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <Label>Nome</Label>
            <Input
              defaultValue={data.name}
              onBlur={(e) => {
                if (e.target.value !== data.name) updateClient.mutate({ name: e.target.value })
              }}
            />
          </div>
          <div>
            <Label>Email</Label>
            <Input
              defaultValue={data.email || ''}
              onBlur={(e) => updateClient.mutate({ email: e.target.value || null })}
            />
          </div>
          <div>
            <Label>Telefone</Label>
            <Input
              defaultValue={data.phone || ''}
              onBlur={(e) => updateClient.mutate({ phone: e.target.value || null })}
            />
          </div>
          <div className="md:col-span-2">
            <Label>Notas</Label>
            <Textarea
              defaultValue={data.notes || ''}
              rows={3}
              onBlur={(e) => updateClient.mutate({ notes: e.target.value || null })}
            />
          </div>
        </div>
      </Card>

      {sub ? (
        <>
          <Card>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Subscription</h2>
              <div className="flex flex-wrap gap-2">
                {[1, 3, 6, 12].map((m) => (
                  <Button key={m} variant="secondary" onClick={() => renew.mutate(m)}>
                    + {m} mês{m > 1 ? 'es' : ''}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <Label>M3U Source</Label>
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-300">
                    {showM3u ? sub.source_m3u_url : '••••••••••••••••'}
                  </code>
                  <Button variant="ghost" onClick={() => setShowM3u((v) => !v)}>
                    {showM3u ? 'Ocultar' : 'Mostrar'}
                  </Button>
                  <Button variant="ghost" onClick={() => testSource.mutate()}>
                    Testar
                  </Button>
                  <Button variant="ghost" onClick={() => refreshPlaylist.mutate()}>
                    Refresh playlist
                  </Button>
                </div>
              </div>
              <div>
                <Label>EPG Source</Label>
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-300">
                    {showEpg ? sub.source_epg_url || '—' : '••••••••••••••••'}
                  </code>
                  <Button variant="ghost" onClick={() => setShowEpg((v) => !v)}>
                    {showEpg ? 'Ocultar' : 'Mostrar'}
                  </Button>
                  <Button variant="ghost" onClick={() => refreshEpg.mutate()}>
                    Refresh EPG
                  </Button>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-300">Upstream (informativo)</h2>
            <p className="mb-4 text-xs text-slate-400">
              Simultaneous stream limits are enforced by the upstream provider. This panel allows provisioning the same
              subscription on multiple devices.
            </p>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-slate-400">Upstream max connections</div>
                <div>{sub.upstream_max_connections ?? '—'}</div>
              </div>
              <div>
                <div className="text-slate-400">Upstream status</div>
                <div>{sub.upstream_status || '—'}</div>
              </div>
              <div>
                <div className="text-slate-400">Upstream expiry</div>
                <div>{formatDate(sub.upstream_expire_at)}</div>
              </div>
              <div>
                <div className="text-slate-400">Notes</div>
                <div>{sub.notes || '—'}</div>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-300">Acesso do cliente</h2>
            <div className="space-y-4">
              <CopyRow label="M3U" value={sub.m3u_url} />
              <CopyRow label="EPG" value={sub.epg_url} />
              <CopyRow label="Stalker Portal URL" value={sub.stalker_portal_url} />
              <CopyRow label="Setup" value={sub.setup_url} />
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">Configuração MAG / Pocket STB</div>
                <div>
                  Portal URL: <code>{sub.stalker_portal_url}</code>
                </div>
                <div className="mt-1 text-slate-400">Use o MAC de cada dispositivo na app. Vários MACs = vários devices.</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (confirm('O token anterior ficará inválido. Continuar?')) regenerateToken.mutate()
                  }}
                >
                  Regenerar token M3U
                </Button>
              </div>
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-3">
              <QrBlock title="M3U" value={sub.m3u_url} />
              <QrBlock title="EPG" value={sub.epg_url} />
              <QrBlock title="Portal" value={sub.stalker_portal_url} />
            </div>
          </Card>

          <Card>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-300">Xtream</h2>
            <div className="space-y-2 text-sm">
              <div>
                <span className="text-slate-400">Server</span>
                <div>{sub.xtream_server}</div>
              </div>
              <div>
                <span className="text-slate-400">Username</span>
                <div>{sub.xtream_username}</div>
              </div>
              <div>
                <span className="text-slate-400">Password</span>
                <div className="flex items-center gap-2">
                  <code>{showXtreamPass ? sub.xtream_password : '••••••••'}</code>
                  <Button variant="ghost" onClick={() => setShowXtreamPass((v) => !v)}>
                    {showXtreamPass ? 'Ocultar' : 'Mostrar'}
                  </Button>
                </div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() =>
                  copyText(
                    `Server: ${sub.xtream_server}\nUsername: ${sub.xtream_username}\nPassword: ${sub.xtream_password}`,
                  )
                }
              >
                Copiar dados
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  if (confirm('A password anterior deixará de funcionar. Continuar?')) regenerateXtream.mutate()
                }}
              >
                Regenerar password Xtream
              </Button>
            </div>
          </Card>
        </>
      ) : null}

      <Card>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-300">Devices</h2>
        <div className="space-y-3">
          {data.devices.map((d) => (
            <div key={d.id} className="rounded-lg border border-slate-800 px-3 py-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-medium">{d.name}</div>
                  <div className="mt-1 space-y-0.5 text-xs text-slate-400">
                    <div>
                      Tipo: {d.device_type} · {d.active ? 'Ativo' : 'Inativo'}
                    </div>
                    <div>MAC: {d.mac_address || '—'}</div>
                    <div>Device ID: {d.device_identifier || '—'}</div>
                    <div>Serial: {d.serial_number || '—'}</div>
                    <div>
                      App: {d.app_name || '—'} {d.app_version ? `v${d.app_version}` : ''}
                    </div>
                    <div>
                      Último visto: {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString('pt-PT') : 'Nunca'} · IP:{' '}
                      {d.last_ip || '—'}
                    </div>
                    <div className="truncate max-w-xl">UA: {d.last_user_agent || '—'}</div>
                  </div>
                </div>
                <Button variant="danger" onClick={() => removeDevice.mutate(d.id)}>
                  Remover
                </Button>
              </div>
            </div>
          ))}
          {data.devices.length === 0 ? <p className="text-sm text-slate-400">Sem dispositivos.</p> : null}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <Input
            placeholder="Nome"
            value={deviceForm.name}
            onChange={(e) => setDeviceForm((p) => ({ ...p, name: e.target.value }))}
          />
          <Select
            value={deviceForm.device_type}
            onChange={(e) => setDeviceForm((p) => ({ ...p, device_type: e.target.value }))}
          >
            {['MAG', 'STALKER', 'ANDROID', 'ANDROID_TV', 'IOS', 'WINDOWS', 'OTHER'].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
          <Input
            placeholder="MAC"
            value={deviceForm.mac_address}
            onChange={(e) => setDeviceForm((p) => ({ ...p, mac_address: e.target.value }))}
          />
          <Button disabled={!deviceForm.name || addDevice.isPending} onClick={() => addDevice.mutate()}>
            + Adicionar dispositivo
          </Button>
        </div>
      </Card>
    </div>
  )
}

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <code className="break-all rounded bg-slate-950 px-2 py-1 text-xs text-slate-300">{value}</code>
        <Button variant="ghost" onClick={() => copyText(value)}>
          Copiar
        </Button>
      </div>
    </div>
  )
}

function QrBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-center">
      <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">{title}</div>
      <div className="inline-flex rounded-md bg-white p-2">
        <QRCodeSVG value={value} size={112} />
      </div>
    </div>
  )
}
