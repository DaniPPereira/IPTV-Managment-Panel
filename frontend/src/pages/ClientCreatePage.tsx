import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button, Card, Input, Label, PageHeader, Select, Textarea } from '@/components/ui'

export function ClientCreatePage() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    notes: '',
    source_m3u_url: '',
    source_epg_url: '',
    starts_at: '',
    expires_at: '',
    max_devices: 2,
    device_name: '',
    mac_address: '',
    device_type: 'OTHER',
  })

  const create = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name,
        email: form.email || null,
        phone: form.phone || null,
        notes: form.notes || null,
        subscription: {
          source_m3u_url: form.source_m3u_url,
          source_epg_url: form.source_epg_url || null,
          starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
          expires_at: new Date(form.expires_at).toISOString(),
          max_devices: Number(form.max_devices),
        },
        device:
          form.device_name || form.mac_address
            ? {
                name: form.device_name || 'Device',
                device_type: form.device_type,
                mac_address: form.mac_address || null,
              }
            : null,
      }
      return (await api.post('/api/admin/clients', payload)).data
    },
    onSuccess: (data) => navigate(`/clients/${data.id}`),
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Falha ao criar cliente')
    },
  })

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div>
      <PageHeader title="Criar cliente" subtitle="Cliente + subscription + dispositivo opcional" />
      <Card className="max-w-3xl">
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            setError('')
            create.mutate()
          }}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label>Nome *</Label>
              <Input required value={form.name} onChange={(e) => set('name', e.target.value)} />
            </div>
            <div>
              <Label>Email</Label>
              <Input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
            </div>
            <div>
              <Label>Telefone</Label>
              <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} />
            </div>
            <div>
              <Label>Máximo de dispositivos</Label>
              <Input
                type="number"
                min={1}
                value={form.max_devices}
                onChange={(e) => set('max_devices', Number(e.target.value))}
              />
            </div>
          </div>
          <div>
            <Label>Notas</Label>
            <Textarea rows={3} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
          </div>
          <div className="border-t border-slate-800 pt-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-300">Subscription</h2>
            <div className="space-y-4">
              <div>
                <Label>M3U Source URL *</Label>
                <Input required value={form.source_m3u_url} onChange={(e) => set('source_m3u_url', e.target.value)} />
              </div>
              <div>
                <Label>EPG Source URL</Label>
                <Input value={form.source_epg_url} onChange={(e) => set('source_epg_url', e.target.value)} />
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>Início</Label>
                  <Input type="datetime-local" value={form.starts_at} onChange={(e) => set('starts_at', e.target.value)} />
                </div>
                <div>
                  <Label>Expiração *</Label>
                  <Input
                    required
                    type="datetime-local"
                    value={form.expires_at}
                    onChange={(e) => set('expires_at', e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-800 pt-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-300">Dispositivo (opcional)</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label>Nome</Label>
                <Input value={form.device_name} onChange={(e) => set('device_name', e.target.value)} placeholder="TV Sala" />
              </div>
              <div>
                <Label>Tipo</Label>
                <Select value={form.device_type} onChange={(e) => set('device_type', e.target.value)}>
                  {['MAG', 'STALKER', 'ANDROID', 'ANDROID_TV', 'IOS', 'WINDOWS', 'OTHER'].map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>MAC</Label>
                <Input value={form.mac_address} onChange={(e) => set('mac_address', e.target.value)} placeholder="00:1A:79:AA:BB:CC" />
              </div>
            </div>
          </div>
          {error ? <p className="text-sm text-red-300">{error}</p> : null}
          <Button disabled={create.isPending}>{create.isPending ? 'A criar…' : 'Criar cliente'}</Button>
        </form>
      </Card>
    </div>
  )
}
