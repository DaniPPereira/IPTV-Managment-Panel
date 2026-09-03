import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button, Card, Input, Label } from '@/components/ui'

export function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const login = useMutation({
    mutationFn: async () => api.post('/api/admin/auth/login', { username, password }),
    onSuccess: () => navigate('/'),
    onError: () => setError('Credenciais inválidas'),
  })

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <div className="mb-6">
          <div className="text-xs uppercase tracking-[0.2em] text-teal-300/80">IPTV Panel</div>
          <h1 className="mt-2 text-2xl font-semibold">Admin login</h1>
          <p className="mt-1 text-sm text-slate-400">Aceda ao painel de provisionamento</p>
        </div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setError('')
            login.mutate()
          }}
        >
          <div>
            <Label>Username</Label>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
          <div>
            <Label>Password</Label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error ? <p className="text-sm text-red-300">{error}</p> : null}
          <Button className="w-full" disabled={login.isPending}>
            {login.isPending ? 'A entrar…' : 'Entrar'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
