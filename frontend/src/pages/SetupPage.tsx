import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import axios from 'axios'
import { copyText, formatDate } from '@/lib/utils'
import { Button, Card, StatusBadge } from '@/components/ui'

type SetupData = {
  client_name: string
  status: string
  expires_at: string
  m3u_url: string
  epg_url: string
  xtream_server: string
  xtream_username: string
  xtream_password: string
}

export function SetupPage() {
  const { token } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['setup', token],
    enabled: !!token,
    queryFn: async () => (await axios.get<SetupData>(`/api/public/setup/${token}`)).data,
  })

  if (isLoading) return <div className="p-8 text-slate-300">A carregar…</div>
  if (error || !data) return <div className="p-8 text-red-300">Acesso não encontrado ou desativado.</div>

  const bundle = `M3U: ${data.m3u_url}\nEPG: ${data.epg_url}\nServer: ${data.xtream_server}\nUsername: ${data.xtream_username}\nPassword: ${data.xtream_password}`

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-4 py-10">
      <Card>
        <div className="text-xs uppercase tracking-[0.2em] text-teal-300/80">IPTV Setup</div>
        <h1 className="mt-2 text-3xl font-semibold">{data.client_name}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <StatusBadge status={data.status} />
          <span>Ativa até {formatDate(data.expires_at)}</span>
        </div>

        <div className="mt-8 space-y-4 text-sm">
          <Row label="M3U" value={data.m3u_url} />
          <Row label="EPG" value={data.epg_url} />
          <Row label="Server" value={data.xtream_server} />
          <Row label="Username" value={data.xtream_username} />
          <Row label="Password" value={data.xtream_password} />
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={() => copyText(bundle)}>Copiar tudo</Button>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-center">
            <div className="mb-2 text-xs uppercase text-slate-400">M3U QR</div>
            <div className="inline-flex rounded bg-white p-2">
              <QRCodeSVG value={data.m3u_url} size={128} />
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-center">
            <div className="mb-2 text-xs uppercase text-slate-400">Setup QR</div>
            <div className="inline-flex rounded bg-white p-2">
              <QRCodeSVG value={window.location.href} size={128} />
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <code className="break-all text-slate-200">{value}</code>
        <Button variant="ghost" onClick={() => copyText(value)}>
          Copiar
        </Button>
      </div>
    </div>
  )
}
