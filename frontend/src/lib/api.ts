import axios from 'axios'

export const api = axios.create({
  baseURL: '',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export type SubscriptionStatus = 'ACTIVE' | 'EXPIRING_SOON' | 'EXPIRED' | 'DISABLED'

export type Paginated<T> = {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export type AdminMe = {
  id: string
  username: string
  must_change_password: boolean
  last_login_at?: string | null
}

export type DashboardStats = {
  clients: { total: number; active: number; disabled: number }
  subscriptions: {
    active: number
    expired: number
    expiring_7_days: number
    expiring_30_days: number
  }
  devices: { total: number; active: number }
}

export type ClientListItem = {
  id: string
  name: string
  email?: string | null
  phone?: string | null
  active: boolean
  status: SubscriptionStatus
  expires_at?: string | null
  device_count: number
  last_access_at?: string | null
  xtream_username?: string | null
}

export type Device = {
  id: string
  client_id: string
  subscription_id?: string | null
  name: string
  device_type: string
  mac_address?: string | null
  device_identifier?: string | null
  serial_number?: string | null
  app_name?: string | null
  app_version?: string | null
  last_seen_identifier?: string | null
  active: boolean
  last_seen_at?: string | null
  last_ip?: string | null
  last_user_agent?: string | null
  created_at: string
  updated_at: string
}

export type Subscription = {
  id: string
  client_id: string
  active: boolean
  starts_at: string
  expires_at: string
  max_devices: number
  upstream_max_connections?: number | null
  upstream_status?: string | null
  upstream_expire_at?: string | null
  notes?: string | null
  public_token: string
  xtream_username: string
  xtream_password: string
  last_access_at?: string | null
  status: SubscriptionStatus
  m3u_url: string
  epg_url: string
  setup_url: string
  stalker_portal_url: string
  xtream_server: string
  source_m3u_url?: string | null
  source_epg_url?: string | null
  created_at: string
  updated_at: string
}

export type ClientDetail = {
  id: string
  name: string
  email?: string | null
  phone?: string | null
  notes?: string | null
  active: boolean
  created_at: string
  updated_at: string
  status: SubscriptionStatus
  current_subscription?: Subscription | null
  devices: Device[]
}

export type AuditLog = {
  id: number
  admin_user_id?: string | null
  action: string
  entity_type: string
  entity_id?: string | null
  details?: string | null
  ip_address?: string | null
  created_at: string
}
