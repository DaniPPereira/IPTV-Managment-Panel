import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('pt-PT')
}

export function formatRelative(value?: string | null) {
  if (!value) return 'Nunca'
  const d = new Date(value)
  const diff = Date.now() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days <= 0) return 'Hoje'
  if (days === 1) return 'Ontem'
  return `${days} dias`
}

export async function copyText(text: string) {
  await navigator.clipboard.writeText(text)
}
