import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button, Card, Input, Label, PageHeader } from '@/components/ui'

export function SettingsPage() {
  const qc = useQueryClient()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState('')

  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: async () => (await api.get('/api/admin/settings')).data,
  })

  const changePassword = useMutation({
    mutationFn: async () =>
      api.post('/api/admin/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    onSuccess: () => {
      setMessage('Password atualizada')
      setCurrentPassword('')
      setNewPassword('')
      qc.invalidateQueries({ queryKey: ['me'] })
    },
    onError: () => setMessage('Não foi possível alterar a password'),
  })

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Configuração da instância e conta admin" />
      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-300">Instância</h2>
        {settings.data ? (
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-slate-400">Public base URL</dt>
              <dd>{settings.data.public_base_url}</dd>
            </div>
            <div>
              <dt className="text-slate-400">Setup page</dt>
              <dd>{settings.data.setup_page_enabled ? 'Ativa' : 'Desativada'}</dd>
            </div>
            <div>
              <dt className="text-slate-400">M3U cache</dt>
              <dd>{settings.data.m3u_cache_seconds}s</dd>
            </div>
            <div>
              <dt className="text-slate-400">EPG cache</dt>
              <dd>{settings.data.epg_cache_seconds}s</dd>
            </div>
          </dl>
        ) : (
          <p className="text-slate-400">A carregar…</p>
        )}
      </Card>
      <Card className="max-w-lg">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-300">Alterar password</h2>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            changePassword.mutate()
          }}
        >
          <div>
            <Label>Password atual</Label>
            <Input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </div>
          <div>
            <Label>Nova password</Label>
            <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} minLength={8} />
          </div>
          {message ? <p className="text-sm text-teal-300">{message}</p> : null}
          <Button disabled={changePassword.isPending}>Guardar</Button>
        </form>
      </Card>
    </div>
  )
}